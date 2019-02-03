# Standard Library Imports
from typing import Union, List, Dict, Any, Tuple, Iterator
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
        self.preselect = cmdargs.preselect
        self.cached = cached
        self.args = cmdargs

        self.display = Display(cmdargs.detailed, cmdargs.no_crop, cached)
        self.pm = PManager(cached)

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
                    self.parent_stack.append(resp)
                    item = items[selector]
                    path = item["path"]

                    # Split up the kodi url
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

    def process_resp(self, resp):  # type: (KodiData) -> List[Dict[str, Any]]
        """Process the resp object and trun into a list of listitems."""

        # Create initial item list with the previous list as the first item
        items = [{"label": "..", "path": self.parent_stack[-1].path}] if self.parent_stack else []

        # Populate list of items
        if resp.listitems:
            items.extend(item[1] for item in resp.listitems)
        elif resp.resolved:
            items.append(resp.resolved)
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

    def show(self, items, current_path):  # type: (List[Dict[str, Any]], str) -> int
        line_width = self.line_width

        # Create output list with headers
        output = ["=" * line_width, current_path, "-" * line_width]

        # Display the list of listitems for user to select
        if self.detailed:
            self.detailed_view(items)
        else:
            lines = self.compact_view(items)
            output.extend(lines)

        output.append("-" * self.line_width)
        print("\n".join(output))

        # Return the full list of listitems
        return self.user_choice(len(items))

    def compact_view(self, items):  # type: (List[Dict[str, Any]]) -> Iterator[str]
        """Displays a list of items along with the index to enable a user to select an item."""

        # Calculate the max length of required lines
        title_len = max(len(item["label"].strip()) for item in items) + 1
        num_len = len(str(len(items)))

        # Create a line output for each listitem entry
        for count, item in enumerate(items):
            item = deepcopy(item)

            # Folder/Video icon, + for Folder, - for Video
            isfolder = item.get("properties", {}).get("folder") == "true"
            item_type = "+" if isfolder else "-"

            # Decode path & context path components
            item["path"] = self.decode_path(item["path"])
            if "context" in item:
                item["context"] = [(name, self.decode_path(command)) for name, command in item["context"]]

            # Remove Label formating
            label = re.sub(r"\[[^\]]+?\]", "", item.pop("label", "UNKNOWN")).strip()
            label = self.localize(label)

            # Construct the output line
            yield "{}. {} {} Listitem({})".format(str(count).rjust(num_len), item_type, label.ljust(title_len), item)

    def detailed_view(self, listitems):
        """
        Displays a list of items along with the index to enable a user to select an item.

        :param list listitems: List of dictionarys containing all of the listitem data.
        :returns: The selected item
        :rtype: dict
        """
        terminal_width = self.terminal_width

        def line_limiter(text):
            if isinstance(text, (bytes, type(u""))):
                text = text.replace("\n", "").replace("\r", "")
            else:
                text = str(text)

            if self.crop and len(text) > (terminal_width - size_of_name):
                return "%s..." % (text[:terminal_width - (size_of_name + 3)])
            else:
                return text

        print("")
        # Print out all listitem to console
        for count, item in enumerate(listitems):
            # Process listitem into a list of property name and value
            process_items = self.process_listitem(item.copy())

            # Calculate the max length of property name
            size_of_name = max(16, *map(len, process_items)) + 1  # Ensures a minimum spaceing of 16

            label = "{}. {}".format(count, process_items.pop("label"))

            if count == 0:
                print("{}".format("#" * self.line_width))
            else:
                print("\n\n{}".format("#" * self.line_width))

            print(line_limiter(label))
            print("{}".format("#" * self.line_width))

            for key, value in process_items.items():
                if isinstance(value, list):
                    print("{}:".format(key.title()))
                    for name, text in value:
                        print("- {}{}".format(name.ljust(size_of_name), text))
                else:
                    print(key.title().ljust(size_of_name), value)

        print("-" * terminal_width)

    def process_listitem(self, item):  # type: (Any) -> Dict[str, List[Tuple[str, str]]]
        label = re.sub(r"\[[^\]]+?\]", "", item.pop("label")).strip()
        buffer = {"label": self.localize(label)}

        if "label2" in item:
            buffer["label2"] = self.localize(item.pop("label2").strip())

        if "path" in item:
            path = item.pop("path")
            if path.startswith("plugin://"):
                buffer["path"] = sub = []

                parts = urlparse.urlsplit(path)

                sub.append(("addon_id", parts.netloc))
                sub.append(("selector", parts.path if parts.path else "/"))

                if parts.query:
                    # Decode query string before parsing
                    query = self.decode_path(parts.query)
                    query = urlparse.parse_qsl(query)
                    sub.extend(query)
            else:
                buffer["path"] = path

        if "context" in item:
            buffer["context"] = [(self.localize(name), self.decode_path(command)) for name, command in item.pop("context")]

        for key, value in item.items():
            if isinstance(value, dict):
                buffer[key] = [(sub_key, sub_value) for sub_key, sub_value in value.items()]
            else:
                buffer["key"] = value

        return buffer

    def user_choice(self, valid_range):  # type: (int) -> Union[int, None]
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
                    print("You entered a non-integer value, Choice must be an integer")
            else:
                return None

            # Check if choice is within the valid range
            if choice <= valid_range:
                print("")
                return choice
            else:
                print("Choise is out of range, Please choose from above list.")

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
