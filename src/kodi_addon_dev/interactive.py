# Standard Library Imports
from typing import Union, Tuple, List
import multiprocessing
import binascii
import argparse
import pickle
import runpy
import json
import sys
import re
import os


from .support import Addon, logger
from .tesseract import Tesseract, KodiData
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
    _input = input_raw
except NameError:
    _input = input


def interactive(cmdargs, cached, url_parts):
    # Keep track of parents
    parent_stack = []  # type: List[urlparse.SplitResult]
    executers = {}

    while url_parts:
        # Request the addon related to kodi plugin url
        addon = cached.request_addon(url_parts.netloc)

        # Reuse executer if available
        if addon.id in executers:
            executer = executers[addon.id]
        else:
            executer = Executer(addon, cached)
            executers[addon.id] = executer

        # Execute addon and check for succesfull execution
        resp = executer.execute(url_parts)
        url_parts = handle_resp(resp, parent_stack, cmdargs, url_parts)
        if url_parts is False:
            break

    # Stop all stored executer processes
    for executer in executers.values():
        executer.close()


class Executer(object):
    def __init__(self, addon, cached):
        self.deps = cached.load_dependencies(addon)
        self.cached = cached
        self.addon = addon
        self.reuse = False
        self._pipe = None

    def subprocess(self):  # type: () -> Tuple[multiprocessing.Process, multiprocessing.Connection]
        if self._pipe:
            return self._pipe
        else:
            # Pips to handle passing of data from and to subprocess
            source_pipe, sub_pipe = multiprocessing.Pipe(duplex=True)

            # Create the new process that will execute the addon
            p = multiprocessing.Process(target=subprocess, args=[sub_pipe, self.reuse])
            p.start()

            # Save the pipe for later use
            resp = (p, source_pipe)
            if self.reuse:
                self._pipe = resp
            return resp

    def execute(self, url_parts):  # type: (urlparse.SplitResult) -> Union[bool, KodiData]
        command = ("execute", (self.addon, self.deps, self.cached, url_parts))
        process, pipe = self.subprocess()
        pipe.send(command)

        # Wait till we receive data from the addon process
        while True:
            status, data = pipe.recv()

            # Check if user input is requested
            if status == "prompt":
                # Prompt the user for input and
                # send it back to the subprocess
                input_data = _input(data)
                pipe.send(input_data)

            else:
                # Check if execution failed
                resp = status if status is False else data
                break

        # Wait for the subprocess to finish before
        # proceeding if it's not going to be reused
        if not self.reuse and process.is_alive():
            process.join()
        return resp

    def close(self):
        """Stop the subproces"""
        if self._pipe:
            stop_command = ("stop", None)
            process, pipe = self._pipe

            # Send stop command
            pipe.send(stop_command)
            process.join()


def subprocess(pipe, reuse):
    # Wait till we receive
    # commands from the executer
    while True:
        # Stop the subprocess
        # This is required when reusing the subprocess
        command, data = pipe.recv()
        if command == "stop":
            break

        # Execute the addon
        elif command == "execute":
            url = data[3]  # type: urlparse.SplitResult
            addon = data[0]  # type: Addon

            # Patch sys.argv to emulate what is expected
            xbmc.session = tesseract = Tesseract(*data[:3], pipe=pipe)
            sys.argv = (urlparse.urlunsplit([url.scheme, url.netloc, url.path, "", ""]), -1, "?{}".format(url.query))

            try:
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


def handle_resp(resp, parent_stack, cmdargs, url_parts):
    if resp is False:
        print("Failed to execute addon. Please check log.")
        try:
            _input("Press enter to continue:")
        except KeyboardInterrupt:
            return False

        # Revert back to previous callback if one exists
        if parent_stack:
            return parent_stack.pop()
        else:
            return False
    else:
        items = process_resp(resp, parent_stack, cmdargs)

        selecter = cmdargs.preselect.pop() if cmdargs.preselect else user_choice(len(items))
        if parent_stack and selecter == 0:
            return parent_stack.pop()
        elif selecter is None:
            return False
        else:
            # Return preselected item or ask user for selection
            parent_stack.append(url_parts)
            item = items[selecter]
            path = item["path"]

            # Split up the kodi url
            return urlparse.urlsplit(path)


def process_resp(resp, parent_stack, cmdargs):
    # type: (KodiData, List[urlparse.SplitResult], argparse.Namespace) -> List[xbmcgui.ListItem]

    # Item list with first item as the previous directory item
    items = [{"label": "..", "path": parent_stack[-1].geturl()}] if parent_stack else []

    # Load all availlable listitems
    if resp.listitems:
        items.extend(item[1] for item in resp.listitems)
    elif resp.resolved:
        items.append(resp.resolved)
        items.extend(resp.playlist)

    # Display the list of listitems for user
    # to select if no pre selection was givin
    if not cmdargs.preselect:
        if cmdargs.compact:
            compact_item_selector(items)
        else:
            detailed_item_selector(items, cmdargs.no_crop)

    # Return the full list of listitems
    return items


def compact_item_selector(listitems):
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


def detailed_item_selector(listitems, no_crop):
    """
    Displays a list of items along with the index to enable a user to select an item.

    :param list listitems: List of dictionarys containing all of the listitem data.
    :param bool no_crop: Disable croping of long lines of text if True, (default => False)
    :returns: The selected item
    :rtype: dict
    """
    terminal_width = max(get_terminal_size((300, 25)).columns, 80)  # Ensures a line minimum of 80

    def line_limiter(text):
        if isinstance(text, (bytes, type(u""))):
            text = text.replace("\n", "").replace("\r", "")
        else:
            text = str(text)

        if no_crop is False and len(text) > (terminal_width - size_of_name):
            return "%s..." % (text[:terminal_width - (size_of_name + 3)])
        else:
            return text

    print("")
    # Print out all listitem to console
    for count, item in enumerate(listitems):
        # Process listitem into a list of property name and value
        process_items = process_listitem(item.copy())

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


def process_listitem(item):
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
            command = re.sub("_(?:pickle|json)_=([0-9a-f]+)", decode_args, command, flags=re.IGNORECASE)
            buffer.append(("- {}".format(name), command))

    for key, value in item.items():
        if isinstance(value, dict):
            buffer.append(("{}:".format(key.title()), ""))
            for sub_key, sub_value in value.items():
                buffer.append(("- {}".format(sub_key), sub_value))
        else:
            buffer.append((key.title(), value))

    return buffer


def decode_args(matchobj):
    hex_type = matchobj.group(0)
    hex_code = matchobj.group(1)

    if hex_type.startswith("_json_"):
        return str(json.loads(binascii.unhexlify(hex_code)))
    elif hex_type.startswith("_pickle_"):
        return str((pickle.loads(binascii.unhexlify(hex_code))))
    else:
        return matchobj.group(1)


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
                print("You entered a non-integer value, Choice must be an integer")
        else:
            return None

        # Check if choice is within the valid range
        if choice <= valid_range:
            return choice
        else:
            print("Choise is out of range, Please choose from above list.")
