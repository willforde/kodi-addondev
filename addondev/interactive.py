# Standard Library Imports
from __future__ import unicode_literals
import multiprocessing
import binascii
import pickle
import json
import sys
import re
import os

try:
    from shutil import get_terminal_size
except NameError:
    from backports.shutil_get_terminal_size import get_terminal_size

try:
    import urllib.parse as urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    import urlparse

# Package imports
from addondev.utils import input_raw, ensure_native_str, unicode_type
from addondev import support


def interactive(pluginpath, preselect=None, content_type="video", compact_mode=False, no_crop=False):
    """
    Execute a given kodi plugin

    :param unicode pluginpath: The path to the plugin to execute.
    :param list preselect: A list of pre selection to make.
    :param str content_type: The content type to list, if more than one type is available. e.g. video, audio
    :param bool compact_mode: If True the listitems view will be compacted, else full detailed. (default => False)
    :param bool no_crop: Disable croping of long lines of text if True, (default => False)
    """
    plugin_id = os.path.basename(pluginpath)
    callback_url = base_url = u"plugin://{}/".format(plugin_id)

    # Keep track of parents so we can have a '..' option to go back
    parent_stack = []

    while callback_url is not None:
        if not callback_url.startswith(base_url):
            raise RuntimeError("callback url is outside the scope of this addon: {}".format(callback_url))

        # Execute the addon in a separate process
        data = execute_addon(pluginpath, callback_url, content_type)
        if data["succeeded"] is False:
            print("Failed to execute addon. Please check log.")
            try:
                input_raw("Press enter to continue:")
            except KeyboardInterrupt:
                break

            # Revert back to previous callback if one exists
            if parent_stack:
                callback_url = parent_stack.pop()
                continue
            else:
                break

        # Item list with first item as the previous directory item
        items = [{"label": "..", "path": parent_stack[-1]}] if parent_stack else []

        # Display listitem selection if listitems are found
        if data["listitem"]:
            items.extend(item[1] for item in data["listitem"])
        elif data["resolved"]:
            items.append(data["resolved"])
            items.extend(data["playlist"][1:])

        # Display the list of listitems for user to select
        if compact_mode:
            selected_item = compact_item_selector(items, callback_url, preselect)
        else:
            selected_item = detailed_item_selector(items, preselect, no_crop)

        if selected_item:
            if parent_stack and selected_item["path"] == parent_stack[-1]:
                callback_url = parent_stack.pop()
            else:
                parent_stack.append(callback_url)
                callback_url = selected_item["path"]
        else:
            break


def execute_addon(*args):
    """
    Executes a add-on in a separate process.

    :returns: A dictionary of listitems and other related results.
    :rtype: dict
    """
    # Pips to handle passing of data from addon process to controler
    pipe_recv, pipe_send = multiprocessing.Pipe(duplex=True)
    process_args = [pipe_send]
    process_args.extend(args)

    # Create the new process that will execute the addon
    p = multiprocessing.Process(target=subprocess, args=process_args)
    p.start()

    # Wait till we receive data from the addon process
    while True:
        data = pipe_recv.recv()
        if "prompt" in data:
            input_data = input_raw(data["prompt"])
            pipe_recv.send(input_data)
        else:
            break

    p.join()
    return data


def subprocess(pipe_send, pluginpath, callback_url, content_type):
    """
    Imports and executes the addon.

    :param pipe_send: The communication object used for sending data back to the initiator.
    :param unicode pluginpath: The path to the plugin to execute.
    :param str callback_url: The url containing the route path and callback params.
    :param str content_type: The content type to list, if more than one type is available.
    """
    addon_data = support.initializer(pluginpath)
    support.data_pipe = pipe_send

    # Splits callback into it's individual components
    scheme, pluginid, selector, params, _ = urlparse.urlsplit(ensure_native_str(callback_url))
    if params:
        params = "?%s" % params

    # Add content_type to params if more than one provider exists
    elif len(addon_data.provides) > 1:
        for ctype in addon_data.provides:
            if content_type == ctype:
                params = "?content_type={}".format(ctype)
                break
        else:
            # Default to the first provider if selected type was not found
            params = "?content_type={}".format(addon_data.provides[0])
            support.logger("Unable to find selected content_type '{}', defaulting to '{}'"
                           .format(content_type, addon_data.provides[0]))

    # Patch sys.argv to emulate what is expected
    sys.argv = (urlparse.urlunsplit([scheme, pluginid, selector, "", ""]), -1, params)

    try:
        addon = __import__(addon_data.entry_point)
        addon.run()
    finally:
        # Send back the results from the addon
        pipe_send.send(support.plugin_data)


def compact_item_selector(listitems, current, preselect):
    """
    Displays a list of items along with the index to enable a user to select an item.

    :param list listitems: List of dictionarys containing all of the listitem data.
    :param current: The current callback url.
    :param list preselect: A list of pre selection to make.
    :returns: The selected item
    :rtype: dict
    """
    # Calculate the max length of required lines
    title_len = max(len(item["label"].strip()) for item in listitems) + 1
    num_len = len(str(len(listitems) - 1))
    line_width = 400
    type_len = 8

    # Create output list with headers
    output = ["",
              "=" * line_width,
              "Current URL: %s" % current,
              "-" * line_width,
              "%s %s %s Listitem" % ("#".center(num_len + 1), "Label".ljust(title_len), "Type".ljust(type_len)),
              "-" * line_width]

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

    # Return preselected item or ask user to selection
    if preselect:
        print("Item %s has been pre-selected.\n" % preselect[0])
        return listitems[preselect.pop(0)]
    else:
        return user_choice(listitems)


def detailed_item_selector(listitems, preselect, no_crop):
    """
    Displays a list of items along with the index to enable a user to select an item.

    :param list listitems: List of dictionarys containing all of the listitem data.
    :param list preselect: A list of pre selection to make.
    :param bool no_crop: Disable croping of long lines of text if True, (default => False)
    :returns: The selected item
    :rtype: dict
    """
    terminal_width = max(get_terminal_size((300, 25)).columns, 80)  # Ensures a line minimum of 80

    def line_limiter(text):
        if isinstance(text, (bytes, unicode_type)):
            text = text.replace("\n", "").replace("\r", "")
        else:
            text = str(text)

        if no_crop is False and len(text) > (terminal_width - size_of_name):
            return "{}...".format(text[:terminal_width - (size_of_name + 3)])
        else:
            return text

    print("")
    # Print out all listitem to console
    for count, item in enumerate(listitems):
        # Process listitem into a list of property name and value
        process_items = process_listitem(item.copy())

        # Calculate the max length of property name
        size_of_name = max(16, *[len(name) for name, _ in process_items])  # Ensures a minimum spaceing of 16

        label = "{}. {}".format(count, process_items.pop(0)[1])
        if count == 0:
            print("{}".format("#" * 80))
        else:
            print("\n\n{}".format("#" * 80))
        
        print(line_limiter(label))
        print("{}".format("#" * 80))

        for key, value in process_items:
            print(key.ljust(size_of_name), line_limiter(value))
    
    print("-" * terminal_width)

    # Return preselected item or ask user to selection
    if preselect:
        print("Item %s has been pre-selected.\n" % preselect[0])
        return listitems[preselect.pop(0)]
    else:
        return user_choice(listitems)


def process_listitem(item):
    label = re.sub("\[[^\]]+?\]", "", item.pop("label")).strip()
    buffer = [("Label", label)]

    if "label2" in item:
        buffer.append(("Label 2", item.pop("label2").strip()))

    if "path" in item:
        path = item.pop("path")
        buffer.append(("Path:", ""))
        if path.startswith("plugin://"):
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
    
    if "context" in item:
        context = item.pop("context")
        buffer.append(("Context:", ""))
        for name, command in context:
            buffer.append(("- {}".format(name), command))

    for key, value in item.items():
        if isinstance(value, dict):
            buffer.append(("{}:".format(key.title()), ""))
            for sub_key, sub_value in value.items():
                buffer.append(("- {}".format(sub_key), sub_value))
        else:
            buffer.append((key.title(), value))

    return buffer


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
            choice = input_raw(prompt)
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
