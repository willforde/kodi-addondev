# Standard Library Imports
from typing import Dict, List
import xbmcgui
import logging
import shutil
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
from . import utils
from .support import Addon, logger, KODI_HOME

# Kodi log levels
log_levels = (logging.DEBUG,  # xbmc.LOGDEBUG
              logging.DEBUG,  # xbmc.LOGINFO
              logging.INFO,  # xbmc.LOGNOTICE
              logging.WARNING,  # xbmc.LOGWARNING
              logging.ERROR,  # xbmc.LOGERROR
              logging.CRITICAL,  # xbmc.LOGSEVERE
              logging.CRITICAL,  # xbmc.LOGFATAL
              logging.DEBUG)  # xbmc.LOGNONE


def setup_env():  # type: () -> Dict[str, str]
    # Kodi directory paths
    paths = {"home": KODI_HOME, "xbmc": KODI_HOME}

    # Kodi userdata paths
    paths["userdata"] = paths["profile"] = paths["masterprofile"] = userdata = os.path.join(KODI_HOME, "userdata")
    paths["videoplaylists"] = os.path.join(userdata, "playlists", "video")
    paths["musicplaylists"] = os.path.join(userdata, "playlists", "music")
    paths["addon_data"] = os.path.join(userdata, "addon_data")
    paths["thumbnails"] = os.path.join(userdata, "Thumbnails")
    paths["database"] = os.path.join(userdata, "Database")

    # Kodi temp paths
    paths["temp"] = temp = os.path.join(KODI_HOME, "temp")
    paths["subtitles"] = temp
    paths["recordings"] = temp
    paths["screenshots"] = temp
    paths["logpath"] = temp
    paths["cdrips"] = temp
    paths["skin"] = temp

    # Ensure that there are no leftover temp directorys
    tmpdir = os.path.dirname(KODI_HOME)
    for filename in os.listdir(tmpdir):
        if filename.startswith("kodi-addondev."):
            filepath = os.path.join(tmpdir, filename)
            shutil.rmtree(filepath, ignore_errors=True)

    # Ensure that all directories exists
    for kodi_path in paths.values():
        if not os.path.exists(kodi_path):
            os.makedirs(kodi_path)

    # The full list of kodi special paths
    return paths


class KodiData(object):
    def __init__(self):
        self._data = {}

    @property
    def sortmethods(self):  # type: () -> List[int]
        return self._data.setdefault("sortmethods", [])

    @property
    def playlist(self):  # type: () -> List[xbmcgui.ListItem]
        return self._data.setdefault("playlist", [])

    @property
    def listitems(self):  # type: () -> List[xbmcgui.ListItem]
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

    def __init__(self, addon, deps, cached, pipe=None):
        self.id = addon.id
        self.data = KodiData()
        self.kodipaths = setup_env()
        self.addons = cached
        self.pipe = pipe

        # Reverse sys path to allow
        # for faster list insertion
        sys.path.reverse()

        # Process all dependencies and download any missing dependencies
        for dep in map(cached.__getitem__, deps):
            if dep.type == "xbmc.python.module":
                path = os.path.join(dep.path, os.path.normpath(dep.library))
                sys.path.append(path)

        # Add plugin addons to sys path as well
        if addon.type == "xbmc.python.pluginsource" and addon.path not in sys.path:
            sys.path.append(addon.path)
        elif addon.type == "xbmc.python.module":
            path = os.path.join(addon.path, os.path.normpath(addon.library))
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
        logger.log(lvl, msg)

    def translate_path(self, path):  # type: (str) -> str
        path = utils.ensure_native_str(path)
        parts = urlparse.urlsplit(path)

        # Return the path unmodified if not a special path
        if not parts.scheme == "special":
            return path

        # Fetch realpath from the path mapper
        try:
            realpath = self.kodipaths[parts.netloc]
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
