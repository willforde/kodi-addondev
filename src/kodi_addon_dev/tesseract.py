# Standard Library Imports
from typing import List, Tuple
import multiprocessing as mp
import xbmcgui
import logging
import sys
import os

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

# Package imports
from kodi_addon_dev import utils
from kodi_addon_dev.repo import LocalRepo
from kodi_addon_dev.support import Addon, base_logger, KPATHS

# Kodi log levels
log_levels = (logging.DEBUG,  # xbmc.LOGDEBUG
              logging.DEBUG,  # xbmc.LOGINFO
              logging.INFO,  # xbmc.LOGNOTICE
              logging.WARNING,  # xbmc.LOGWARNING
              logging.ERROR,  # xbmc.LOGERROR
              logging.CRITICAL,  # xbmc.LOGSEVERE
              logging.CRITICAL,  # xbmc.LOGFATAL
              logging.DEBUG)  # xbmc.LOGNONE


class KodiData(object):
    def __init__(self):
        self.calling_item = None
        self.path = None  # type: str
        self._data = {}

    @property
    def sortmethods(self):  # type: () -> List[int]
        return self._data.setdefault("sortmethods", [])

    @property
    def playlist(self):  # type: () -> List[xbmcgui.ListItem]
        return self._data.setdefault("playlist", [])

    @property
    def listitems(self):  # type: () -> List[Tuple[str, xbmcgui.ListItem, bool]]
        return self._data.setdefault("listitems", [])

    @property
    def resolved(self):  # type: () -> xbmcgui.ListItem
        return self._data.get("resolved", None)

    @resolved.setter
    def resolved(self, resolved):  # type: (xbmcgui.ListItem) -> None
        self._data["resolved"] = resolved

    @property
    def contenttype(self):  # type: () -> str
        return self._data.get("contenttype", None)

    @contenttype.setter
    def contenttype(self, contenttype):  # type: (str) -> None
        self._data["contenttype"] = contenttype

    @property
    def category(self):  # type: () -> str
        return self._data.get("category", None)

    @category.setter
    def category(self, category):  # type: (str) -> None
        self._data["category"] = category

    @property
    def succeeded(self):  # type: () -> bool
        return self._data.get("succeeded", False)

    @succeeded.setter
    def succeeded(self, succeeded):  # type: (bool) -> None
        self._data["succeeded"] = succeeded

    @property
    def updatelisting(self):  # type: () -> bool
        return self._data.get("updatelisting", None)

    @updatelisting.setter
    def updatelisting(self, updatelisting):  # type: (bool) -> None
        self._data["updatelisting"] = updatelisting

    def clear(self):
        self._data.clear()


class Tesseract(object):
    """
    Process running addon and all it's dependencies.

    :param Addon addon: The currently running add-on.
    :param pipe: The connection pipe to use when running under a separate process
    :type pipe: multiprocessing.Connection
    """

    # TODO: Add support for 'xbmc.service' plugins

    def __init__(self, addon, deps, cached, pipe=None):  # type: (Addon, List[str], LocalRepo, mp.connection) -> None
        self.data = KodiData()
        self.addons = cached
        self.id = addon.id
        self.pipe = pipe

        # Reverse sys path to allow
        # for faster list insertion
        sys.path.reverse()

        if "xbmc.python.module" in addon.extensions:
            library = addon.extensions["xbmc.python.module"]["library"]
            path = os.path.join(addon.path, os.path.normpath(library))
            sys.path.append(path)

        # Add plugin addons to sys path as well
        if addon.entrypoint:
            lib_path, _ = addon.entrypoint
            if lib_path not in sys.path:
                sys.path.append(lib_path)

        # Process all dependencies and download any missing dependencies
        for dep in map(cached.__getitem__, deps):
            if "xbmc.python.module" in dep.extensions:
                library = dep.extensions["xbmc.python.module"]["library"]
                path = os.path.join(dep.path, os.path.normpath(library))
                sys.path.append(path)

        # Reverse the path list again
        # to change it back to normal
        sys.path.reverse()

    def __contains__(self, addon_id):
        return addon_id in self.addons

    def get_addon(self, addon_id=None):  # type: (str) -> Addon
        return self.addons[addon_id if addon_id else self.id]

    @staticmethod
    def log(lvl, msg):  # type: (int, str) -> None
        lvl = log_levels[lvl]
        base_logger.log(lvl, msg)

    @staticmethod
    def translate_path(path):  # type: (str) -> str
        path = utils.ensure_native_str(path)
        parts = urlparse.urlsplit(path)

        # Return the path unmodified if not a special path
        if not parts.scheme == "special":
            return path

        # Fetch realpath from the path mapper
        try:
            realpath = KPATHS[parts.netloc]
        except KeyError:
            raise ValueError("%s is not a valid special directory" % parts.netloc)
        else:
            return os.path.join(realpath, os.path.normpath(parts.path))

    def input(self, prompt):  # type: (str) -> str
        """
        Ask the user a question and return the answer.
        Works even when running under a separate process.
        """
        pipe = self.pipe
        if pipe:
            request = ("prompt", prompt)
            pipe.send(request)
            return pipe.recv()
        else:
            return _input(prompt)
