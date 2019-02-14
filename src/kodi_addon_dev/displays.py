from __future__ import print_function

# Standard Library Imports
from typing import List, Iterator, NamedTuple, NoReturn
from functools import partial
from copy import deepcopy
import binascii
import argparse
import pickle
import json
import abc
import re

# Package imports
from kodi_addon_dev.repo import LocalRepo
from kodi_addon_dev.support import logger
from kodi_addon_dev.utils import ensure_native_str, urlparse, real_input
import xbmcgui

try:
    from shutil import get_terminal_size
except ImportError:
    # noinspection PyUnresolvedReferences
    from backports.shutil_get_terminal_size import get_terminal_size

# The Processed Listitem Named tuple, Make listitems easier to work with
Listitem = NamedTuple("Listitem", (("count", int), ("isfolder", bool), ("size_of_name", int), ("item", dict)))

__all__ = ["BaseDisplay", "CMDisplay"]


class BaseDisplay(object):
    """Base Class to for Displaying Kodi Listitems."""
    __metaclass__ = abc.ABCMeta

    def __init__(self, cached, settings):  # type: (LocalRepo, argparse.Namespace) -> NoReturn
        self.settings = settings
        self.cached = cached

    @abc.abstractmethod
    def input(self, msg):  # type: (str) -> str
        pass

    @abc.abstractmethod
    def notify(self, *msg, **kwargs):
        pass

    @abc.abstractmethod
    def show(self, items, current_path):  # type: (List[Listitem], str) -> Listitem
        pass

    def show_raw(self, items, current_path):  # type: (List[xbmcgui.ListItem], str) -> int
        size_of_name = [16]
        pro_items = []

        # Make a deepcopy of all item so not to messup the parent list
        for count, item in enumerate(map(deepcopy, items)):
            prop = item.get("properties", {})
            isfolder = prop["isplayable"] != "true" if "isplayable" in prop else prop.get("folder", "true") == "true"
            label = re.sub(r"\[[^\]]+?\]", "", item.pop("label", "UNKNOWN")).strip()
            label = self._formatter(label)
            size_of_name.append(len(label))
            buffer = {"label": label}

            # Process the path independently
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
                    query = self._decode_path(parts.query)
                    query = urlparse.parse_qsl(query)

                    size_of_name.append(len(query[0]))
                    buffer["Params"] = dict(query)
            else:
                # Just show the path itself
                buffer["url"] = path

            # Process the context menu items independently
            if "context" in item:
                context = {self._formatter(name): self._decode_path(command) for name, command in item.pop("context")}
                size_of_name.extend(map(len, (name for name in context)))
                buffer["context"] = context

            # Strip out formating for selective data
            if "info" in item and "plot" in item["info"]:
                item["info"]["plot"] = self._formatter(item["info"]["plot"])
            if "label2" in item:
                item["label2"] = self._formatter(item["label2"])

            # Show all leftover items
            for key, value in item.items():
                key = self._formatter(key)
                size_of_name.append(len(key))

                # Show the sub name and values
                if isinstance(value, dict):
                    buffer[key] = sub = {}
                    for sname, svalue in value.items():
                        sub[sname] = svalue
                        size_of_name.append(len(sname))
                else:
                    # Just directly show the value
                    buffer["key"] = value

            # Return the buffer and max length of the title column
            listitem = Listitem(count, isfolder, max(size_of_name) + 1, buffer)
            pro_items.append(listitem)

        # Show the list to user and return the id of the selected item
        selected_item = self.show(pro_items, current_path)
        return selected_item.count

    # noinspection PyTypeChecker
    def _formatter(self, text):
        """Convert kodi formating into real text"""
        text = ensure_native_str(text)

        # Search & replace localization strings
        text = re.sub(r"\$LOCALIZE\[(\d+)\]", self._localize, text)
        text = re.sub(r"\$ADDON\[(\S+?)\s(\d+)\]", self._localize_addon, text)
        text = re.sub(r"\[COLOR\s\w+\](.+?)\[/COLOR\]", partial(self.formatter, "COLOR"), text)

        # Common formatting
        for common in ("I", "B", "UPPERCASE", "LOWERCASE", "CAPITALIZE", "LIGHT"):
            text = re.sub(r"\[{0}\](.+?)\[/{0}\]".format(common), partial(self.formatter, common), text)

        return text.replace("[CR]", "\n")

    @staticmethod
    def formatter(name, match):
        """
        Convert a kodi formating.

        :param str name: The name of the formatting e.g. UPPERCASE, B, COLOR
        :param match: A re.Match object with the matching text located at group(1), group(0) for the full text.

        :returns: The formatted string
        :rtype: str
        """
        # Strip out formating and reutrn text untouched
        if name in ("B", "I", "LIGHT", "COLOR"):
            return match.group(1)

        elif name == "UPPERCASE":
            return match.group(1).upper()
        elif name == "LOWERCASE":
            return match.group(1).lower()
        elif name == "CAPITALIZE":
            return match.group(1).capitalize()
        else:
            return match.group(0)

    def _localize(self, match):
        """$LOCALIZE[12345] - for specifying a localized string."""
        string_id = int(match.group(1))
        text = match.group(0)
        return self.__localize(text, string_id, "resource.language.en_gb")

    def _localize_addon(self, match):
        """$ADDON[script.music.foobar 12345] - for specifying a string provided by an addon."""
        text = match.group(0)
        addon_id = match.group(1)
        string_id = int(match.group(2))
        return self.__localize(text, string_id, addon_id)

    def __localize(self, text, string_id, addon_id):  # type: (str, int, str) -> str
        """Return the localized string if available else leave string untouched"""
        strings = self.cached.request_addon(addon_id).strings
        return strings[string_id] if string_id in strings else text

    @staticmethod
    def _decode_path(path):  # type: (str) -> str
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


class CMDisplay(BaseDisplay):
    """Display manager that will display kodi listitem in a basic non tty terminal window."""

    def __init__(self, cached, settings):  # type: (LocalRepo, argparse.Namespace) -> NoReturn
        super(CMDisplay, self).__init__(cached, settings)
        self.default_terminal_size = 80

    def input(self, msg):  # type: (str) -> str
        """Ask for user input."""
        try:
            return real_input(msg)
        except KeyboardInterrupt:
            return ""

    @staticmethod
    def notify(*msg, **kwargs):
        """
        Notify the user with givin message.

        If skip is set to True then the user will be asked if they want to continue, returning True if so.
        Else False will be returned.
        """
        skip = kwargs.get("skip", True)
        print(*msg)
        if skip:
            try:
                real_input("Press enter to continue, or Ctrl+C to Quit:")
            except KeyboardInterrupt:
                return False
            else:
                print()
                return True
        else:
            return False

    def show(self, items, current_path):  # type: (List[Listitem], str) -> Listitem
        """Show a list of all the avilable listitems and allow user to make there selection."""
        # Process all listitems into a Tuple of [count, isfolder, len label, listitem]
        lines = self._detailed_view(items) if self.settings.detailed else self._compact_view(items)
        lines = lines if self.settings.no_crop else map(self._line_limiter, lines)
        terminal_width = self._terminal_width

        # Construct the full list of line to display
        output = ["=" * terminal_width, current_path, "=" * terminal_width]
        output.extend(lines)
        output.append("=" * terminal_width)
        print("\n".join(output))

        # Return the full list of listitems
        return self._user_choice(items)

    @staticmethod
    def _compact_view(items):  # type: (List[Listitem]) -> Iterator[str]
        """Display listitems in a compact view, one line per listitem."""

        # Calculate the max length of required lines
        title_len = max(item.size_of_name for item in items)
        num_len = len(str(len(items)))
        title_len += num_len + 4

        # Create a line output for each listitem entry
        for count, isfolder, _, item in items:
            # Folder/Video icon, + for Folder, - for Video
            label = ("{}. + {}" if isfolder else "{}. - {}").format(str(count).rjust(num_len), item.pop("label"))
            yield "{} Listitem({})".format(label.ljust(title_len), item)

    def _detailed_view(self, items):  # type: (List[Listitem]) -> Iterator[str]
        """Display listitems in a detailed view, each component of a listitem will be on it's own line."""
        terminal_width = self._terminal_width

        # Create a line output for each component of a listitem
        for count, _, size_of_name, item in items:
            # Show the title in it's own area
            yield "{}. {}".format(count, item.pop("label"))
            yield "#" * terminal_width

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
    def _user_choice(items):  # type: (List[Listitem]) -> Listitem
        """Ask user to select an item, returning selection as an integer."""
        while True:
            try:
                # Ask user for selection, Returning None if user entered nothing
                choice = real_input("Choose an item: ")
            except KeyboardInterrupt:
                break

            if choice:
                try:
                    # Convert choice to an integer
                    choice = int(choice)
                except ValueError:
                    print("You entered a non-numerical value, Plean enter a numerical value or leave black to exit.")
                else:
                    try:
                        return items[choice]
                    except IndexError:
                        print("Choise is out of range, Please choose from above list.")
            else:
                break

    @property
    def _terminal_width(self):
        """Ensures a line minimum of 80."""
        return max(get_terminal_size((300, 25)).columns, 80)

    def _line_limiter(self, line):  # type: (str) -> str
        """Limit the length of a output line to fit within the terminal window."""
        terminal_width = self._terminal_width
        return "%s..." % (line[:terminal_width-3]) if len(line) > terminal_width else line
