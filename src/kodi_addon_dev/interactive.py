# Standard Library Imports
from typing import Union, List, Dict, Tuple, Iterator, Any
import multiprocessing as mp
from copy import deepcopy
import binascii
import argparse
import pickle
import runpy
import json
import sys
import re
import os

# Package imports
from kodi_addon_dev.repo import LocalRepo
from kodi_addon_dev.support import Addon, logger
from kodi_addon_dev.utils import ensure_native_str
from kodi_addon_dev.tesseract import Tesseract, KodiData
import xbmcgui
import xbmc

try:
    from shutil import get_terminal_size
except ImportError:
    # noinspection PyUnresolvedReferences
    from backports.shutil_get_terminal_size import get_terminal_size

try:
    import urllib.parse as urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    import urlparse

try:
    # noinspection PyUnresolvedReferences
    _input = raw_input
except NameError:
    _input = input


def subprocess(pipe, reuse):  # type: (mp.connection, bool) -> None
    try:
        # Wait till we receive
        # commands from the executer
        while True:
            # Stop the subprocess
            # This is required when reusing the subprocess
            command, data = pipe.recv()  # type: (str, Tuple[Addon, List[str], LocalRepo, urlparse.SplitResult])
            if command == "stop":
                break

            # Execute the addon
            elif command == "execute":
                addon, deps, cached, url = data
                # Patch sys.argv to emulate what is expected
                urllist = [url.scheme, url.netloc, url.path, "", ""]
                sys.argv = (urlparse.urlunsplit(urllist), -1, "?{}".format(url.query))

                try:
                    # Create tesseract to handle kodi module interactions
                    xbmc.session = tesseract = Tesseract(addon, deps, cached, pipe=pipe)
                    tesseract.data.path = url.geturl()

                    # Execute the addon
                    path = os.path.splitext(addon.library)[0]
                    runpy.run_module(path, run_name="__main__", alter_sys=False)

                # Addon must have directly raised an error
                except Exception as e:
                    logger.debug(e, exc_info=True)
                    pipe.send((False, False))

                else:
                    # Send back the results from the addon
                    resp = (tesseract.data.succeeded, tesseract.data)
                    pipe.send(resp)

            # If this subprocess will not be reused then
            # break from loop to end the process
            if reuse is False:
                break

    except BaseException as e:
        logger.debug(e, exc_info=True)
        pipe.send((False, False))


class PRunner(object):
    def __init__(self, cached, addon):  # type: (LocalRepo, Addon) -> None
        self.deps = cached.load_dependencies(addon)
        self.reuse = True  # addon.reuse_lang_invoker
        self.cached = cached
        self.addon = addon

        # Pipes to handle passing of data to and from the subprocess
        self.pipe, self.sub_pipe = mp.Pipe(duplex=True)
        self._process = None  # type: mp.Process

    @property
    def process(self):  # type: () -> mp.Process
        if self._process and self._process.is_alive():
            return self._process
        else:
            # Create the new process that will execute the addon
            process = mp.Process(target=subprocess, args=[self.sub_pipe, self.reuse])
            process.start()

            if self.reuse:
                # Save the process for later use
                self._process = process
            return process

    def execute(self, url_parts):  # type: (urlparse.SplitResult) -> Union[KodiData, bool]
        try:
            # Construct command and send to sub process for execution
            command = ("execute", (self.addon, self.deps, self.cached, url_parts))
            process, pipe = self.process, self.pipe
            pipe.send(command)

            # Wait till we receive data from the addon process
            while process.is_alive():
                # Wait to receive data from pipe before continuing
                # If no data was received within one second, check
                # to make sure that the process is still alive
                if pipe.poll(1):
                    status, data = pipe.recv()
                else:
                    continue

                # Check if user input is requested
                if status == "prompt":
                    # Prompt the user for input and
                    # send it back to the subprocess
                    try:
                        input_data = _input(data)
                    except KeyboardInterrupt:
                        pipe.send("")
                    else:
                        pipe.send(input_data)

                else:
                    # Check if execution failed before returning
                    return False if status is False else data

        except Exception as e:
            logger.debug(e, exc_info=True)

        # SubProcess exited unexpectedly
        return False

    def stop(self):
        """Stop the subproces."""
        if self._process and self._process.is_alive():
            # Send stop command
            stop_command = ("stop", None)
            self.pipe.send(stop_command)
            self._process.join()


class PManager(dict):
    def __init__(self, cached):  # type: (LocalRepo) -> None
        super(PManager, self).__init__()
        self.cached = cached

    def __missing__(self, addon):  # type: (Addon) -> PRunner
        self[addon] = runner = PRunner(self.cached, addon)
        return runner

    def close(self):
        """Stop all saved runners"""
        for runner in self.values():
            runner.stop()


class Interact(object):
    def __init__(self, cmdargs, cached):  # type: (argparse.Namespace, LocalRepo) -> None
        self.parent_stack = []  # type: List[KodiData]
        self.cached = cached
        self.args = cmdargs

        self.display = Display(cmdargs.detailed, cmdargs.no_crop, cached)
        self.pm = PManager(cached)

        # Reverse the list of preselection for faster access
        self.preselect = list(map(int, cmdargs.preselect))
        self.preselect.reverse()

    def start(self, request):  # type: (urlparse.SplitResult) -> None
        try:
            while request:
                if isinstance(request, urlparse.SplitResult):
                    # Request the addon & process manager related to the kodi plugin id
                    addon = self.cached.request_addon(request.netloc)
                    runner = self.pm[addon]  # type: PRunner

                    # Execute addon in subprocess
                    resp = runner.execute(request)
                    if resp is False:
                        request = self.handle_failed()
                        continue
                else:
                    # This must be the parent object
                    resp = request

                # Process the response and convert into a list of items
                items = self.process_resp(resp)
                selector = self.preselect.pop() if self.preselect else self.display.show(items, resp.path)

                # Fetch the selected listitem and start the loop again
                if selector == 0 and self.parent_stack:
                    request = self.parent_stack.pop()
                elif selector is None:
                    break
                else:
                    # Return preselected item or ask user for selection
                    item = items[selector]
                    path = item["path"]

                    # Split up the kodi url
                    resp.calling_item = deepcopy(item)
                    self.parent_stack.append(resp)
                    request = urlparse.urlsplit(path)

        except KeyboardInterrupt:
            pass

        # except Exception as e:
        #     logger.debug(e, exc_info=True)
        #     print("Sorry :(, Something went really wrong.")

        # Stop all stored saved processes
        self.pm.close()

    def handle_failed(self):  # type: () -> Union[KodiData, bool]
        """
        Report to user that addon has failed to execute.
        Returning previous list if one exists.
        """
        print("Failed to execute addon. Please check log.")

        # Parse script and wait for user input
        # then revert back to previous list if one exists
        try:
            _input("Press enter to continue:")
        except KeyboardInterrupt:
            return False
        else:
            return self.parent_stack.pop() if self.parent_stack else False

    def process_resp(self, resp):  # type: (KodiData) -> List[xbmcgui.ListItem]
        """Process the resp object and trun into a list of listitems."""

        items = []
        # Populate list of items
        if resp.listitems:
            if self.parent_stack:
                item = {"label": "..", "path": self.parent_stack[-1].path}
                items.append(item)
            items.extend(item[1] for item in resp.listitems)
        elif resp.resolved:
            # Add resolved video
            if self.parent_stack:
                base = self.parent_stack[-1].calling_item
                base.pop("context")
                base.update(resp.resolved)
                items.append(base)
            else:
                items.append(resp.resolved)

            # Add the playlist
            items.extend(resp.playlist)

        # Return the full list of listitems
        return items


class Display(object):
    def __init__(self, detailed, no_crop, cached):  # type: (bool, bool, LocalRepo) -> None
        self.detailed = detailed
        self.crop = not no_crop
        self.cached = cached
        self.line_width = 80

    @property
    def terminal_width(self):
        """Ensures a line minimum of 80."""
        return max(get_terminal_size((300, 25)).columns, 80)

    def show(self, items, current_path):  # type: (List[xbmcgui.ListItem], str) -> int
        # Process all listitems into a Tuple of [count, isfolder, len label, listitem]
        items = self.process_listitems(items)
        lines = self.detailed_view(items) if self.detailed else self.compact_view(items)
        lines = map(self.line_limiter, lines) if self.crop else lines

        # Construct the full list of line to display
        output = ["=" * self.line_width, current_path, "-" * self.line_width]
        output.extend(lines)
        output.append("=" * self.line_width)
        print("\n".join(output))

        # Return the full list of listitems
        return self.user_choice(len(items))

    def process_listitems(self, items):
        # type: (List[xbmcgui.ListItem]) -> List[Tuple[int, bool, int, Dict[str, List[Tuple[str, str]]]]]
        size_of_name = [16]
        pro_items = []

        # Make a deepcopy of all item so not to messup the parent list
        for count, item in enumerate(map(deepcopy, items)):
            isfolder = item.get("properties", {}).get("folder", "true") == "true"
            label = re.sub(r"\[[^\]]+?\]", "", item.pop("label", "UNKNOWN")).strip()
            label = self.localize(label)
            size_of_name.append(len(label))
            buffer = {"label": label}

            # Process the path independently
            if "path" in item:
                path = item.pop("path")
                if path.startswith("plugin://"):
                    buffer["url"] = sub = {}

                    # Show the base url components
                    parts = urlparse.urlsplit(path)
                    sub["id"] = parts.netloc
                    sub["path"] = parts.path if parts.path else "/"

                    # Parse the list of query parameters
                    if parts.query:
                        # Decode query string before parsing
                        query = self.decode_path(parts.query)
                        query = urlparse.parse_qsl(query)

                        size_of_name.append(len(query[0]))
                        buffer["Params"] = dict(query)
                else:
                    # Just show the path itself
                    buffer["path"] = path

            # Process the context menu items independently
            if "context" in item:
                context = {self.localize(name): self.decode_path(command) for name, command in item.pop("context")}
                size_of_name.extend(map(len, (name for name in context)))
                buffer["context"] = context

            # Show all leftover items
            for key, value in item.items():
                key = self.localize(key)
                size_of_name.append(len(key))

                # Show the sub name and values
                if isinstance(value, dict):
                    buffer[key] = sub = {}
                    for sname, svalue in value.items():
                        sname = self.localize(sname)
                        sub[sname] = self.localize(svalue) if isinstance(svalue, (bytes, type(u""))) else svalue
                        size_of_name.append(len(sname))
                else:
                    # Just directly show the value
                    buffer["key"] = value

            # Return the buffer and max length of the title column
            pro_items.append((count, isfolder, max(size_of_name) + 1, buffer))

        # Return the full list of processed listitems
        return pro_items

    def process_listitems_old(self, items):
        # type: (List[xbmcgui.ListItem]) -> List[Tuple[int, bool, int, Dict[str, List[Tuple[str, str]]]]]
        size_of_name = [16]
        pro_items = []

        # Make a deepcopy of all item so not to messup the parent list
        for count, item in enumerate(map(deepcopy, items)):
            isfolder = item.get("properties", {}).get("folder", "true") == "true"
            label = re.sub(r"\[[^\]]+?\]", "", item.pop("label", "UNKNOWN")).strip()
            label = self.localize(label)
            size_of_name.append(len(label))
            buffer = {"label": label}

            # Process the path independently
            if "path" in item:
                path = item.pop("path")
                if path.startswith("plugin://"):
                    buffer["url"] = sub = []

                    # Show the base url components
                    parts = urlparse.urlsplit(path)
                    sub.append(("addon_id", parts.netloc))
                    sub.append(("path", parts.path if parts.path else "/"))

                    # Parse the list of query parameters
                    if parts.query:
                        # Decode query string before parsing
                        query = self.decode_path(parts.query)
                        query = urlparse.parse_qsl(query)

                        size_of_name.append(len(query[0]))
                        buffer["Params"] = query
                else:
                    # Just show the path itself
                    buffer["path"] = path

            # Process the context menu items independently
            if "context" in item:
                context = [(self.localize(name), self.decode_path(command)) for name, command in item.pop("context")]
                size_of_name.extend(map(len, (name for name, _ in context)))
                buffer["context"] = context

            # Show all leftover items
            for key, value in item.items():
                key = self.localize(key)
                size_of_name.append(len(key))

                # Show the sub name and values
                if isinstance(value, dict):
                    buffer[key] = sub = []
                    for sname, svalue in value.items():
                        sname = self.localize(sname)
                        sub.append((sname, self.localize(svalue) if isinstance(svalue, (bytes, type(u""))) else svalue))
                        size_of_name.append(len(sname))
                else:
                    # Just directly show the value
                    buffer["key"] = value

            # Return the buffer and max length of the title column
            pro_items.append((count, isfolder, max(size_of_name) + 1, buffer))

        # Return the full list of processed listitems
        return pro_items

    @staticmethod
    def compact_view(items):  # type: (Any) -> Iterator[str]
        """Display listitems in a compact view, one line per listitem."""

        # Calculate the max length of required lines
        title_len = max(item[2] for item in items)
        num_len = len(str(len(items)))
        title_len += num_len + 4

        # Create a line output for each listitem entry
        for count, isfolder, _, item in items:
            # Folder/Video icon, + for Folder, - for Video
            label = ("{}. + {}" if isfolder else "{}. - {}").format(str(count).rjust(num_len), item.pop("label"))
            yield "{} Listitem({})".format(label.ljust(title_len), item)

    def detailed_view(self, items):  # type: (Any) -> Iterator[str]
        """Display listitems in a detailed view, each component of a listitem will be on it's own line."""
        # Create a line output for each component of a listitem
        for count, _, size_of_name, item in items:
            # Show the title in it's own area
            yield "{}. {}".format(count, item.pop("label"))
            yield "#" * self.line_width

            # Show all the rest of the listitem
            for key, value in item.items():
                if isinstance(value, dict):
                    yield ("{}:".format(key.title())).ljust(size_of_name)
                    for name, sub in value.items():
                        yield "- {}{}".format(name.ljust(size_of_name), sub)
                else:
                    yield "{}{}".format(key.title().ljust(size_of_name), value)

            yield ""

    @staticmethod
    def decode_path(path):  # type: (str) -> str
        def decode(match):
            key = match.group(1)  # First part of params
            value = match.group(2)  # Second part of params

            try:
                # Decode values from a binascii encoded object
                if key == "_json_":
                    value = json.loads(binascii.unhexlify(value))
                elif key == "_pickle_":
                    value = pickle.loads(binascii.unhexlify(value))

            # Ignore any errors and just return the match untouched
            except Exception as e:
                logger.exception(e)
                return match.group(0)

            else:
                # Reconstruct the url component
                return "{}={}".format(key, value)

        # Search & replace matching values
        path = ensure_native_str(path)
        return re.sub(r"(_pickle_|_json_)=([0-9a-f]+)", decode, path, flags=re.IGNORECASE)

    def localize(self, text):
        def decode(match):
            # Localize the localization string
            strings = self.cached.request_addon("resource.language.en_gb").strings
            string_id = int(match.group(1))

            # Return the localized string if available else leave string untouched
            return strings[string_id] if string_id in strings else match.group(0)

        # Search & replace matching LOCALIZE strings
        text = ensure_native_str(text)
        return re.sub(r"\$LOCALIZE\[(\d+)\]", decode, text)

    def line_limiter(self, line):  # type: (str) -> str
        """Limit the length of a output line to fit within the terminal window."""
        terminal_width = self.terminal_width
        return "%s..." % (line[:terminal_width-3]) if len(line) > terminal_width else line

    @staticmethod
    def user_choice(valid_range):  # type: (int) -> Union[int, None]
        """Ask user to select an item, returning selection as an integer."""
        while True:
            try:
                # Ask user for selection, Returning None if user entered nothing
                choice = _input("Choose an item: ")
            except KeyboardInterrupt:
                return None

            if choice:
                try:
                    # Convert choice to an integer
                    choice = int(choice)
                except ValueError:
                    print("You entered a non-numerical value, Plean enter a numerical value or leave black to exit.")
                else:
                    # Check if choice is within the valid range
                    if choice <= valid_range:
                        print("")
                        return choice
                    else:
                        print("Choise is out of range, Please choose from above list.")
            else:
                return None
