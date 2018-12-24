# Standard Library Imports
from typing import Iterator, Dict
from xml.dom import minidom
import logging
import os

# Package imports
from addondev import support2, utils
from addondev.support2 import ETree, KODI_PATHS

# Python 2 compatibility
if not utils.PY3:
    from codecs import open

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
    def __init__(self, addon, addons):  # type: (support2.Addon, Iterator[support2.Addon]) -> None
        self.addons = {dep.id: dep.preload() for dep in addons}  # type: Dict[str, dict]
        self.addons[addon.id] = addon.preload()
        self.id = addon.id
        self.data = {}

    def __contains__(self, item):
        return item in self.addons

    def get_addon(self, addon_id):  # type: (str) -> Addon
        data = self.addons[addon_id]
        return Addon(data)

    @staticmethod
    def log(lvl, msg):  # type: (int, str) -> None
        lvl = log_levels[lvl]
        support2.logger.log(lvl, msg)

    @staticmethod
    def translate_path(path):  # type: (str) -> str
        path = utils.ensure_native_str(path)
        parts = utils.urlparse.urlsplit(path)

        # Return the path unmodified if not a special path
        if not parts.scheme == "special":
            return path

        # Extract the directory name
        special_path = parts.netloc

        # Fetch realpath from the path mapper
        realpath = KODI_PATHS.get(special_path, None)
        if realpath is None:
            raise ValueError("%s is not a valid root dir" % special_path)
        else:
            return os.path.join(realpath, os.path.normpath(parts.path))


class Addon(object):
    def __init__(self, data):
        self._data = data

    def get_info(self, item):  # type: (str) -> str
        """Returns the value of an addon property as a string."""
        if item in self._data:
            value = self._data[item]
        elif item in self._data["metadata"]:
            value = self._data["metadata"][item]
        elif item in self._data["metadata"]["assets"]:
            value = self._data["metadata"]["assets"][item]
            value = os.path.join(self._data["path"], os.path.normpath(value))
        else:
            return str()

        # Make sure that we always return the native str
        # type of the running python version
        return utils.ensure_native_str(value)

    def set_setting(self, key, value):
        if not isinstance(value, (bytes, utils.unicode_type)):
            raise TypeError("argument 'value' for method 'setSetting' must be unicode or str not '%s'" % type(value))

        spath = os.path.join(self._data["profile"], "settings.xml")
        if os.path.exists(spath):
            # Load in settings xml object
            tree = ETree.parse(spath).getroot()

            # Check for a pre existing setting for given key and remove it
            pre_existing = tree.find("./setting[@id='%s']" % key)
            if pre_existing is not None:
                tree.remove(pre_existing)

        else:
            # Create plugin data directory if don't exist
            settings_dir = os.path.dirname(spath)
            if not os.path.exists(settings_dir):
                os.makedirs(settings_dir)

            # Create settings xml object
            tree = ETree.Element("settings")

        # Add setting to list of xml elements
        ETree.SubElement(tree, "setting", {"id": key, "value": value})

        # Recreate the settings.xml file
        raw_xml = minidom.parseString(ETree.tostring(tree)).toprettyxml(indent=" "*4)
        with open(spath, "w", encoding="utf8") as stream:
            stream.write(raw_xml)

        # Update local store and return
        self._data["settings"][id] = value
        return True

    @property
    def strings(self):
        return self._data["strings"]

    @property
    def settings(self):
        return self._data["settings"]
