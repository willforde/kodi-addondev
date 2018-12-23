# Standard Library Imports
from collections import OrderedDict
from typing import Iterator, Tuple, Dict
import tempfile
import logging
import shutil
import sys
import os
import re

# Third party imports
import appdirs

# Package imports
from addondev import utils

# Optimized imports
try:
    import xml.etree.cElementTree as ETree
except ImportError:
    import xml.etree.ElementTree as ETree


# Python 2 compatibility
if not utils.PY3:
    from codecs import open

# Base logger
logger = logging.getLogger("cli")
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(logging.Formatter("%(relativeCreated)-13s %(levelname)7s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# List of dependencies to ignore
IGNORE_LIST = ("xbmc.python", "xbmc.core", "kodi.resource")

# Supported extension points
EXT_POINTS = ("xbmc.python.pluginsource", "xbmc.python.module")

# Kodi directory paths
KODI_PATHS = OrderedDict()
KODI_PATHS["home"] = home = tempfile.mkdtemp(prefix="kodi-addondev.")
KODI_PATHS["userdata"] = userdata = os.path.join(home, "userdata")
KODI_PATHS["addon_data"] = os.path.join(userdata, "addon_data")
KODI_PATHS["temp"] = os.path.join(home, "temp")
KODI_PATHS["addons"] = cache_dir = appdirs.user_cache_dir("kodi-addondev")
KODI_PATHS["packages"] = os.path.join(cache_dir, "packages")

# Ensure that there are no leftover temp directorys
tmpdir = os.path.dirname(home)
for filename in os.listdir(tmpdir):
    if filename.startswith("kodi-addondev."):
        filepath = os.path.join(tmpdir, filename)
        shutil.rmtree(filepath, ignore_errors=True)

# Ensure that all directories exists
for kodi_path in KODI_PATHS.values():
    if not os.path.exists(kodi_path):
        os.makedirs(kodi_path)


class Dependency(object):
    """Dataclass of addon dependencies."""
    __slots__ = ("id", "version", "optional")

    # noinspection PyShadowingBuiltins
    def __init__(self, id, version, optional=False):  # type: (str, str, bool) -> None
        self.optional = optional
        self.version = version
        self.id = id

    def __eq__(self, other):
        return other.id == self.id

    def repr(self):
        return "Dependency(id={}, version={}, optional={})".format(self.id, self.version, self.optional)


class Addon(object):
    @classmethod
    def from_file(cls, xml_path):  # type: (str) -> Addon
        """Load addon data from addon.xml"""
        xml_node = ETree.parse(xml_path).getroot()
        return cls(xml_node, os.path.dirname(xml_path))

    def __init__(self, xml_node, path=""):  # type: (ETree.Element, str) -> None
        # Parse base info
        self._xml = xml_node
        self._data = data = xml_node.attrib.copy()
        data["author"] = data.pop("provider-name")
        data["profile"] = self.profile = os.path.join(KODI_PATHS["userdata"], data["id"])
        data["path"] = self.path = path

        # Parse entry point
        for ext in xml_node.findall("extension"):
            point = ext.get("point")
            if point in EXT_POINTS:
                data["type"] = point
                data["library"] = ext.get("library")
                data["provides"] = ext[0].text if len(ext) else ""
                break
        else:
            raise RuntimeError("unspoorted addon type")

        # Parse dependencies
        data["requires"] = requires = []
        for imp in xml_node.findall("requires/import"):
            addon_id = imp.get("addon")
            if addon_id not in IGNORE_LIST:
                dep = Dependency(addon_id, imp.get("version"), imp.get("optional", "false") == "true")
                requires.append(dep)

        # Presets
        self.id = data["id"]
        self.version = data["version"]
        self.dependencies = requires
        self.type = data["type"]

    def preload(self):  # type: () -> Dict
        # Parse metadata
        self._data["metadata"] = metadata = {"assets": {}}
        for node in self._xml.find("./extension[@point='xbmc.addon.metadata']"):
            if node.tag == "assets":
                metadata[node.tag] = assets = {sub.tag: sub.text for sub in node}
                if "screenshot" in assets:
                    assets["screenshot"] = [sshot.text for sshot in node.findall("screenshot")]
            elif node.text is not None:
                metadata[node.tag] = node.text

        # Map changelog to news
        metadata["changelog"] = metadata.get("news", "")

        # Preload strings & settings
        self._data["settings"] = dict(self._settings())  # type: Dict[str, str]
        self._data["strings"] = dict(self._strings())  # type: Dict[int, str]
        return self._data

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
        string_loc = [os.path.join(res_path, "strings.po"),
                      os.path.join(res_path, "language", "English", "strings.po"),
                      os.path.join(res_path, "language", "resource.language.en_gb", "strings.po")]

        # Return the first strings.po file that is found
        for path in string_loc:
            if os.path.exists(path):
                # Extract the strings from the strings.po file
                with open(path, "r", "utf-8") as stream:
                    file_data = stream.read()

                # Populate dict of strings
                search_pattern = 'msgctxt\s+"#(\d+)"\s+msgid\s+"(.+?)"\s+msgstr\s+"(.*?)'
                for strID, msgID, msStr in re.findall(search_pattern, file_data):
                    yield int(strID), msStr if msStr else msgID
