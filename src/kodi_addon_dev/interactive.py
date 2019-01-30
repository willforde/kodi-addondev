# Standard Library Imports
from typing import Union, List, Dict, Any, Tuple
import multiprocessing as mp
import binascii
import argparse
import pickle
import runpy
import json
import sys
import re
import os

from .repo import LocalRepo
from .support import Addon, logger
from .tesseract import Tesseract, KodiData
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
    _input = input_raw
except NameError:
    _input = input


def subprocess(pipe, reuse):  # type: (mp.Connection, bool) -> None
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
            sys.argv = (urlparse.urlunsplit([url.scheme, url.netloc, url.path, "", ""]), -1, "?{}".format(url.query))

            try:
                # Create tesseract to handle kodi module interactions
                xbmc.session = tesseract = Tesseract(addon, deps, cached, pipe=pipe)
                tesseract.data.path = url.geturl()

                # Execute the addon
                path = os.path.splitext(addon.library)[0]
                runpy.run_module(path, run_name="__main__", alter_sys=False)

            # Addon must have directly raised an error
            except Exception as e:
                logger.exception(e)
                pipe.send((False, False))

            else:
                # Send back the results from the addon
                resp = (tesseract.data.succeeded, tesseract.data)
                pipe.send(resp)

        # If this subprocess will not be reused then
        # break from loop to end the process
        if reuse is False:
            break


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

    def execute(self, url_parts):  # type: (urlparse.SplitResult) -> KodiData
        # Construct command and send to sub process for execution
        command = ("execute", (self.addon, self.deps, self.cached, url_parts))
        process, pipe = self.process, self.pipe
        pipe.send(command)

        # Wait till we receive data from the addon process
        while True:
            # TODO: Look into timeouts for pipes
            status, data = pipe.recv()

            # Check if user input is requested
            if status == "prompt":
                # Prompt the user for input and
                # send it back to the subprocess
                input_data = _input(data)
                pipe.send(input_data)

            else:
                # Check if execution failed before breaking
                resp = False if status is False else data
                break

        # Wait for the subprocess to finish before
        # proceeding if it's not going to be reused
        if not self.reuse and process.is_alive():
            process.join()
        return resp

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

        self.display = Display(cmdargs.compact, cmdargs.no_crop)
        self.pm = PManager(cached)

    def start(self, request):  # type: (urlparse.SplitResult) -> None
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
            selector = self.preselect.pop() if self.preselect else self.display.show(items)

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

        # Stop all stored saved processes
        self.pm.close()

    def handle_failed(self):  # type: () -> Union[KodiData, bool]
        """
        Report to user that addon has failed to execute.
        Returning previous list if one exists.
        """
        # TODO: Setup logger to log to a file
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
    def __init__(self, compact, no_crop):  # type: (bool, bool) -> None
        self.crop = not no_crop
        self.compact = compact

    def show(self, items):  # type: (List[Dict[str, Any]]) -> int
        # Display the list of listitems for user
        # to select if no pre selection was givin
        if self.compact:
            self.compact_item_selector(items)
        else:
            self.detailed_item_selector(items)

        # Return the full list of listitems
        return self.user_choice(len(items))

    def compact_item_selector(self, listitems):
        """
        Displays a list of items along with the index to enable a user to select an item.

        :param list listitems: List of dictionarys containing all of the listitem data.
        :returns: The selected item
        :rtype: dict
        """
        # Calculate the max length of required lines
        title_len = max(len(item["label"].strip()) for item in listitems) + 1
        num_len = len(str(len(listitems) - 1))
        line_width = 400
        type_len = 8

        # # Create output list with headers
        # output = ["",
        #           "=" * line_width,
        #           "Current URL: %s" % current,
        #           "-" * line_width,
        #           "%s %s %s Listitem" % ("#".center(num_len + 1), "Label".ljust(title_len), "Type".ljust(type_len)),
        #           "-" * line_width]
        output = []

        # Create a line output for each listitem entry
        for count, item in enumerate(listitems):
            label = re.sub(r"\[[^\]]+?\]", "", item.pop("label")).strip()

            if item["path"].startswith("plugin://"):
                if item.get("properties", {}).get("isplayable") == "true":
                    item_type = "video"
                elif label == ".." or item.get("properties", {}).get("folder") == "true":
                    item_type = "folder"
                else:
                    item_type = "script"
            else:
                item_type = "playable"

            line = "{}. {} {} Listitem({})".format(str(count).rjust(num_len), label.ljust(title_len),
                                                   item_type.ljust(type_len), item)
            output.append(line)

        output.append("-" * line_width)
        print("\n".join(output))

    def detailed_item_selector(self, listitems):
        """
        Displays a list of items along with the index to enable a user to select an item.

        :param list listitems: List of dictionarys containing all of the listitem data.
        :returns: The selected item
        :rtype: dict
        """
        terminal_width = max(get_terminal_size((300, 25)).columns, 80)  # Ensures a line minimum of 80

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
            size_of_name = max(16, *[len(name) for name, _ in process_items])  # Ensures a minimum spaceing of 16

            label = "%s. %s" % (count, process_items.pop(0)[1])
            if count == 0:
                print("{}".format("#" * 80))
            else:
                print("\n\n{}".format("#" * 80))

            print(line_limiter(label))
            print("{}".format("#" * 80))

            for key, value in process_items:
                print(key.ljust(size_of_name), line_limiter(value))

        print("-" * terminal_width)

    def process_listitem(self, item):
        label = re.sub(r"\[[^\]]+?\]", "", item.pop("label")).strip()
        buffer = [("Label", label)]

        if "label2" in item:
            buffer.append(("Label 2", item.pop("label2").strip()))

        if "path" in item:
            path = item.pop("path")
            if path.startswith("plugin://"):
                buffer.append(("Path:", ""))
                parts = urlparse.urlsplit(path)
                buffer.append(("- pluginid", parts.netloc))
                if parts.path:
                    buffer.append(("- selecter", parts.path))

                if parts.query:
                    query = urlparse.parse_qsl(parts.query)
                    for key, value in query:
                        if key == "_json_":
                            data = json.loads(binascii.unhexlify(value))
                            if isinstance(data, dict):
                                query.extend(data.items())
                        elif key == "_pickle_":
                            data = pickle.loads(binascii.unhexlify(value))
                            if isinstance(data, dict):
                                query.extend(data.items())
                        else:
                            buffer.append(("- {}".format(key), value))
            else:
                buffer.append(("Path", path))

        if "context" in item:
            context = item.pop("context")
            buffer.append(("Context:", ""))
            for name, command in context:
                command = re.sub(r"_(?:pickle|json)_=([0-9a-f]+)", self.decode_args, command, flags=re.IGNORECASE)
                buffer.append(("- {}".format(name), command))

        for key, value in item.items():
            if isinstance(value, dict):
                buffer.append(("{}:".format(key.title()), ""))
                for sub_key, sub_value in value.items():
                    buffer.append(("- {}".format(sub_key), sub_value))
            else:
                buffer.append((key.title(), value))

        return buffer

    def decode_args(self, matchobj):
        hex_type = matchobj.group(0)
        hex_code = matchobj.group(1)

        if hex_type.startswith("_json_"):
            return str(json.loads(binascii.unhexlify(hex_code)))
        elif hex_type.startswith("_pickle_"):
            return str((pickle.loads(binascii.unhexlify(hex_code))))
        else:
            return matchobj.group(1)

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
                return choice
            else:
                print("Choise is out of range, Please choose from above list.")
