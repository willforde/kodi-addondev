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

from . import repo
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
            if status == "prompt":
                input_data = _input(data)
                pipe.send(input_data)
            elif status is False:
                resp = False
                break
            else:
                resp = data
                break

        if not self.reuse:
            process.join()
        return resp

    def close(self):
        """Stop the subproces"""
        if self._pipe:
            stop_command = ("stop", None)
            process, pipe = self._pipe

            pipe.send(stop_command)
            process.join()


def subprocess(pipe, reuse):
    # Wait till we receive
    # commands from the executer
    while True:
        command, data = pipe.recv()
        if command == "stop":
            break

        elif command == "execute":
            url = data[3]  # type: urlparse.SplitResult
            addon = data[0]  # type: Addon

            # Patch sys.argv to emulate what is expected
            xbmc.session = tesseract = Tesseract(*data[:3], pipe=pipe)
            sys.argv = (urlparse.urlunsplit([url.scheme, url.netloc, url.path, "", ""]), -1, "?{}".format(url.query))

            # Execute the addon
            try:
                runpy.run_path(os.path.join(addon.path, addon.library), run_name="__main__")
            except Exception as e:
                logger.exception(e)
                pipe.send((False, None))
            else:
                # Send back the results from the addon
                resp = (tesseract.data.succeeded, tesseract.data)
                pipe.send(resp)

        # Break from loop to end the process
        if reuse is False:
            break


def interactive(cmdargs):  # type: (argparse.Namespace) -> None
    """Execute a given kodi plugin in interactive mode."""
    # Load the given addon
    # raise ValueError if addon is not valid
    addon = Addon.from_path(cmdargs.addon)
    cached = repo.LocalRepo(cmdargs.local_repos, cmdargs.remote_repos, addon)

    # Create base kodi url
    query = "content_type={}".format(cmdargs.content_type) if cmdargs.content_type else ""
    # noinspection PyArgumentList
    url_parts = urlparse.SplitResult("plugin", addon.id, "/", query, "")

    # Convert any preselection into a list of selections
    preselect = list(map(int, map(str.strip, cmdargs.preselect.split(",")))) if cmdargs.preselect else None
    preselect.reverse()

    # Keep track of parents
    parent_stack = []
    executers = {}

    while url_parts:
        addon = cached.request_addon(url_parts.netloc)

        if addon.id in executers:
            executer = executers[addon.id]
        else:
            executer = Executer(addon, cached)
            executers[addon.id] = executer

        # Execute addon and check for succesfull execution
        resp = executer.execute(url_parts)
        if resp is False:
            print("Failed to execute addon. Please check log.")
            try:
                _input("Press enter to continue:")
            except KeyboardInterrupt:
                break

            # Revert back to previous callback if one exists
            if parent_stack:
                url_parts = parent_stack.pop()
            else:
                break
        else:
            url_parts = process_resp(resp, parent_stack, preselect, cmdargs)
            if not url_parts:
                break

    # Stop all stored executer processes
    for executer in executers.values():
        executer.close()


def process_resp(resp, parent_stack, preselect, cmdargs):
    # type: (KodiData, List, List, argparse.Namespace) -> Union[bool, urlparse.SplitResult]

    # Item list with first item as the previous directory item
    items = [{"label": "..", "path": parent_stack[-1]}] if parent_stack else []

    # Load all availlable listitems
    if resp.listitems:
        items.extend(item[1] for item in resp.listitems)
    elif resp.resolved:
        items.append(resp.resolved)
        items.extend(resp.playlist)

    # Display the list of listitems for user
    # to select if no pre selection was givin
    if not preselect:
        if cmdargs.compact_mode:
            compact_item_selector(items)
        else:
            detailed_item_selector(items, cmdargs.no_crop)

    # Return preselected item or ask user for selection
    item = items[preselect.pop()] if preselect else user_choice(items)
    if item:
        path = item["path"]
        return urlparse.urlsplit(path)
    else:
        return False


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
        label = re.sub("\[[^\]]+?\]", "", item.pop("label")).strip()

        if item["path"].startswith("plugin://"):
            if item.get("properties", {}).get("isplayable") == "true":
                item_type = "video"
            elif label == ".." or item.get("properties", {}).get("folder") == "true":
                item_type = "folder"
            else:
                item_type = "script"
        else:
            item_type = "playable"

        line = "%s. %s %s %s" % (str(count).rjust(num_len), label.ljust(title_len), item_type.ljust(type_len), item)
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


def user_choice(items):
    """
    Returns the selected item from provided items or None if nothing was selected.

    :param list items: List of items to choice from
    :returns: The selected item
    :rtype: dict
    """
    prompt = "Choose an item: "
    while True:
        try:
            # Ask user for selection, Returning None if user entered nothing
            choice = _input(prompt)
            if not choice:
                return None

            # Convert choice to an integer and reutrn the selected item
            choice = int(choice)
            item = items[choice]

            # Return the item if it's a plugin path
            if item["path"].startswith("plugin://"):
                print("")
                return item
            else:
                prompt = "Selection is not a valid plugin path, Please choose again: "

        except ValueError:
            prompt = "You entered a non-integer, Choice must be an integer: "
        except IndexError:
            prompt = "You entered an invalid integer, Choice must be from above list: "
        except (EOFError, KeyboardInterrupt):
            # User skipped the prompt
            return None
