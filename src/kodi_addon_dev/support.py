# Standard Library Imports
from typing import Iterator, Tuple, List, Dict
import xml.etree.ElementTree as ETree
from codecs import open as _open
from xml.dom import minidom
import hashlib
import tempfile
import logging
import shutil
import re
import os

# Third party imports
import appdirs

# Package imports
from kodi_addon_dev import utils

IGNORE_LIST = ("xbmc.python", "xbmc.core", "kodi.resource")
EXT_POINTS = ("xbmc.python.pluginsource", "xbmc.python.module")
CACHE_DIR = appdirs.user_cache_dir("kodi-addondev")

# Kodi directory paths
KODI_HOME = os.path.join(tempfile.gettempdir(), "kodi-addondev.WM_Esa")
KPATHS = {"home": KODI_HOME, "xbmc": KODI_HOME}

# Kodi userdata paths
KPATHS["userdata"] = KPATHS["profile"] = KPATHS["masterprofile"] = userdata = os.path.join(KODI_HOME, "userdata")
KPATHS["videoplaylists"] = os.path.join(userdata, "playlists", "video")
KPATHS["musicplaylists"] = os.path.join(userdata, "playlists", "music")
KPATHS["addon_data"] = os.path.join(userdata, "addon_data")
KPATHS["thumbnails"] = os.path.join(userdata, "Thumbnails")
KPATHS["database"] = os.path.join(userdata, "Database")

# Kodi temp paths
KPATHS["temp"] = temp = os.path.join(KODI_HOME, "temp")
KPATHS["subtitles"] = temp
KPATHS["recordings"] = temp
KPATHS["screenshots"] = temp
KPATHS["logpath"] = temp
KPATHS["cdrips"] = temp
KPATHS["skin"] = temp

# Base logger
base_logger = logging.getLogger("kodi")
base_logger.setLevel(logging.DEBUG)
base_logger.propagate = False

# Add File Handler support to logger
logfile = os.path.join(temp, "kodi.log")
handler = logging.FileHandler(logfile, mode="w", encoding="utf8")
handler.setFormatter(utils.CustomFormatter())
handler.setLevel(logging.DEBUG)
base_logger.addHandler(handler)

# Internal Logger
logger = logging.getLogger("kodi.dev")


def setup_paths(clean):  # type: (bool) -> None
    """Ensure that the mock kodi directory is setup and cleaned if required."""
    if clean:
        shutil.rmtree(KODI_HOME)

    # Ensure that all directories exists
    # The use of 'set' is to remove duplicate directory for to speed up loop
    for kodi_path in set(KPATHS.values()):
        if not os.path.exists(kodi_path):
            os.makedirs(kodi_path)


class Dependency(object):
    """Dataclass of addon dependencies."""
    __slots__ = ("id", "version", "optional")

    # noinspection PyShadowingBuiltins
    def __init__(self, id, version, optional=False):  # type: (str, str, bool) -> None
        self.optional = optional  # type: bool
        self.version = version  # type: str
        self.id = id  # type: str

    def __eq__(self, other):
        return other.id == self.id

    def repr(self):
        return "Dependency(id={}, version={}, optional={})".format(self.id, self.version, self.optional)


class Addon(object):
    @classmethod
    def from_path(cls, path):
        # Load the given addon path, raise ValueError if addon is not valid
        xml_path = os.path.join(path, "addon.xml")
        if os.path.exists(xml_path):
            return cls.from_file(xml_path)
        else:
            raise ValueError("'{}' is not a valid kodi addon, missing 'addon.xml'".format(path))

    @classmethod
    def from_file(cls, xml_path):  # type: (str) -> Addon
        """Load addon data from addon.xml"""
        xml_node = ETree.parse(xml_path).getroot()
        return cls(xml_node, os.path.dirname(xml_path))

    def __init__(self, xml_node, path=""):  # type: (ETree.Element, str) -> None
        self.settings = None  # type: Dict[str, str]
        self.strings = None  # type: Dict[int, str]
        self._xml = xml_node
        self.path = path
        self.stars = -1

        # Parse entry point
        self.type = self._point_type()

    def _point_type(self):
        """Return the extention point type of the addon."""
        for ext in self._xml.findall("extension"):
            point = ext.get("point")
            if point in EXT_POINTS:
                return point
        else:
            return ""

    @property
    def id(self):  # type: () -> str
        return self._xml.get("id")

    @property
    def version(self):  # type: () -> str
        return self._xml.get("version")

    @property
    def author(self):  # type: () -> str
        return self._xml.get("provider-name", "")

    @property
    def name(self):  # type: () -> str
        return self._xml.get("name")

    @property
    def profile(self):  # type: () -> str
        return os.path.join(KPATHS["addon_data"], self.id)

    @property
    def description(self):  # type: () -> str
        return self._text_lang("description")

    @property
    def disclaimer(self):  # type: () -> str
        return self._text_lang("disclaimer")

    @property
    def summary(self):  # type: () -> str
        return self._text_lang("summary")

    @property
    def reuse_lang_invoker(self):  # type: () -> bool
        node = self._xml.find("extension/reuselanguageinvoker")
        if node is None:
            return False
        else:
            return node.text.lower() == "true"

    def _text_lang(self, name):  # type: (str) -> str
        # Attemp to find elements with en_GB first then fallback to en_US if not found.
        for lang_opt in ("en_GB", "en_US", "en"):
            node = self._xml.find("./extension/{0}[@lang='{1}']".format(name, lang_opt))
            if node is not None:
                return node.text

        # Fallback to the first match and return that
        node = self._xml.find("./extension/{0}".format(name))
        if node is not None:
            return node.text
        else:
            return ""

    @property
    def fanart(self):  # type: () -> str
        return self._asset("fanart", "jpg")

    @property
    def icon(self):  # type: () -> str
        return self._asset("icon", "png")

    def _asset(self, name, ext):  # type: (str, str) -> str
        asset = self._xml.find("extension/assets/{}".format(name))
        if asset is not None:
            return os.path.join(self.path, os.path.normpath(asset.text))
        else:
            path = os.path.join(self.path, "{}.{}".format(name, ext))
            return path if os.path.exists(path) else ""

    @property
    def changelog(self):  # type: () -> str
        news = self._xml.find("extension/news")
        if news is not None:
            return news.text.strip()
        else:
            changelog_file = os.path.join(self.path, "changelog-{}.txt".format(self.version))
            if os.path.exists(changelog_file):
                with open(changelog_file, "r", encoding="utf8") as stream:
                    return stream.read().strip()
            else:
                return ""

    def get_info(self, name):  # type: (str) -> str
        """Returns the value of an addon property as a string."""
        value = getattr(self, name, "")
        return utils.ensure_native_str(value)

    @property
    def dependencies(self):  # type: () -> List[Dependency]
        dependencies = []
        for imp in self._xml.findall("requires/import"):
            addon_id = imp.get("addon")
            if addon_id not in IGNORE_LIST:
                dep = Dependency(addon_id, imp.get("version"), imp.get("optional", "false") == "true")
                dependencies.append(dep)
        return dependencies

    def preload(self):  # type: () -> Addon
        """
        Preload the setting & strings into memory.
        This is done to minimize overheads within the addon.
        """
        if self.settings is None:
            self.settings = dict(self._settings())
        if self.strings is None:
            self.strings = dict(self._strings())
        return self

    def _settings(self):  # type: () -> Iterator[Tuple[str, str]]
        # Populate settings from both addon source settings and addon saved profile settings file
        spaths = (os.path.join(self.path, "resources", "settings.xml"), os.path.join(self.profile, "settings.xml"))
        for settings_path in spaths:
            if os.path.exists(settings_path):
                xmldata = ETree.parse(settings_path).getroot()
                for setting in xmldata.findall(".//setting"):
                    yield setting.get("id"), setting.get("value", setting.get("default", ""))

    def _strings(self):  # type: () -> Iterator[Tuple[int, str]]
        # Possible locations for english strings.po
        res_path = os.path.join(self.path, "resources")
        string_loc = [os.path.join(res_path, "language", "resource.language.en_gb", "strings.po"),
                      os.path.join(res_path, "language", "resource.language.en_us", "strings.po"),
                      os.path.join(res_path, "language", "English", "strings.po"),
                      os.path.join(res_path, "strings.po")]

        # Return the first strings.po file that is found
        for path in string_loc:
            if os.path.exists(path):
                # Extract the strings from the strings.po file
                with _open(path, "r", encoding="utf-8") as stream:
                    file_data = stream.read()

                # Populate dict of strings
                search_pattern = r'msgctxt\s+"#(\d+)"\s+msgid\s+"(.+?)"\s+msgstr\s+"(.*?)'
                for strID, msgID, msStr in re.findall(search_pattern, file_data):
                    yield int(strID), msStr if msStr else msgID

    @property
    def library(self):  # type: () -> str
        """Return The library value for the given addon point."""
        node = self._xml.find("extension[@point='{}']".format(self.type))
        if node is not None:
            return node.attrib["library"]
        else:
            raise RuntimeError("library parmeter is missing from extension point")

    def set_setting(self, key, value):
        if not isinstance(value, (bytes, utils.unicode_type)):
            raise TypeError("argument 'value' for method 'setSetting' must be unicode or str not '%s'" % type(value))

        path = os.path.join(self.profile, "settings.xml")
        if os.path.exists(path):
            # Load in settings xml object
            tree = ETree.parse(path).getroot()

            # Check for a pre existing setting for given key and remove it
            pre_existing = tree.find("./setting[@id='%s']" % key)
            if pre_existing is not None:
                tree.remove(pre_existing)

        else:
            # Create plugin data directory if don't exist
            settings_dir = os.path.dirname(path)
            if not os.path.exists(settings_dir):
                os.makedirs(settings_dir)

            # Create settings xml object
            tree = ETree.Element("settings")

        # Add setting to list of xml elements
        ETree.SubElement(tree, "setting", {"id": key, "value": value})

        # Recreate the settings.xml file
        raw_xml = minidom.parseString(ETree.tostring(tree)).toprettyxml(indent=" "*4)
        with _open(path, "w", encoding="utf8") as stream:
            stream.write(raw_xml)

        # Update local store and return
        self.settings[key] = value

    def __eq__(self, other):
        return other.id == self.id

    def __repr__(self):
        return "Addon(id={})".format(self.id)

    def __hash__(self):
        addon_id = self.id if isinstance(self.id, bytes) else self.id.encode("utf8")
        return int(hashlib.sha256(addon_id).hexdigest(), 16)
