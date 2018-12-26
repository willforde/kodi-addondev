# Standard Library Imports
from typing import Dict
import logging
import sys
import os

try:
    import urllib.parse as urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    import urlparse

# Package imports
from addondev import repo, utils
from addondev.support import Addon, logger, KODI_PATHS

# Kodi log levels
log_levels = (logging.DEBUG,  # xbmc.LOGDEBUG
              logging.DEBUG,  # xbmc.LOGINFO
              logging.INFO,  # xbmc.LOGNOTICE
              logging.WARNING,  # xbmc.LOGWARNING
              logging.ERROR,  # xbmc.LOGERROR
              logging.CRITICAL,  # xbmc.LOGSEVERE
              logging.CRITICAL,  # xbmc.LOGFATAL
              logging.DEBUG)  # xbmc.LOGNONE


class Dataset(object):
    """
    Process running addon and all it's dependencies.

    :param str addon_path: Path to the add-on.
    :param list repos: List of unofficial kodi repos to use.
    """

    def __init__(self, addon_path, repos):
        # Add custom kodi repos to repo list
        if repos:
            repo.REPOS.extend(repos)

        # Load the given addon path, raise ValueError if addon is not valid
        xml_path = os.path.join(addon_path, "addon.xml")
        if os.path.exists(xml_path):
            addon = Addon.from_file(xml_path)
        else:
            raise ValueError("'{}' is not a valid kodi addon, missing 'addon.xml'".format(addon_path))

        # Reverse sys path to allow
        # for faster list insertion
        sys.path.reverse()

        self.id = addon.id
        self.addons = {addon.id: addon.preload()}  # type: Dict[str, Addon]

        # Process all dependencies and download any missing dependencies
        for dep in repo.process_dependencies(addon.dependencies):
            self.addons[dep.id] = dep.preload()

            if dep.type == "xbmc.python.module":
                path = os.path.join(dep.path, os.path.normpath(dep.library))
                sys.path.append(path)

        # Reverse the path list again
        # to change it back to normal
        sys.path.reverse()

    def __contains__(self, addon_id):
        return addon_id in self.addons

    def get_addon(self, addon_id=None):  # type: (str) -> Addon
        return self.addons[addon_id if self.addons[addon_id] else self.id]

    @staticmethod
    def log(lvl, msg):  # type: (int, str) -> None
        lvl = log_levels[lvl]
        logger.log(lvl, msg)

    @staticmethod
    def translate_path(path):  # type: (str) -> str
        path = utils.ensure_native_str(path)
        parts = urlparse.urlsplit(path)

        # Return the path unmodified if not a special path
        if not parts.scheme == "special":
            return path

        # Extract the directory name
        special_path = parts.netloc

        # Fetch realpath from the path mapper
        try:
            realpath = KODI_PATHS[special_path]
        except KeyError:
            raise ValueError("%s is not a valid root dir" % special_path)
        else:
            return os.path.join(realpath, os.path.normpath(parts.path))
