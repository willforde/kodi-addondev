# Standard Library Imports
from collections import OrderedDict
from typing import List
import tempfile
import logging
import shutil
import sys
import os

# Third party imports
import appdirs

# Package imports
from addondev import utils

# Optimized imports
try:
    import xml.etree.cElementTree as ETree
except ImportError:
    import xml.etree.ElementTree as ETree

# Base logger
logger = logging.getLogger("cli")
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(logging.Formatter("%(relativeCreated)-13s %(levelname)7s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# List of dependencies to ignore
IGNORE_LIST = ("xbmc.python", "xbmc.core", "kodi.resource")

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
    __slots__ = ("id", "version")

    def __init__(self, addon_id, version):  # type: (str, str) -> None
        self.version = version
        self.id = addon_id

    def __eq__(self, other):
        return other.id == self.id


class Addon(object):
    @classmethod
    def from_file(cls, xml_path):  # type: (str) -> Addon
        xml_node = ETree.parse(xml_path).getroot()
        obj = cls(xml_node)
        obj.path = os.path.dirname(xml_path)
        return obj

    def __init__(self, xml_node):  # type: (ETree.Element) -> None
        self._xml = xml_node
        self.path = ""

        # Extract required data from addon.xml
        self.id = xml_node.attrib["id"]
        self.version = xml_node.attrib["version"]

    @property
    def dependencies(self):  # type: () -> List[Dependency]
        """
        List of required plugins needed for this addon to work.

        :returns: A list of Dependency objects consisting of (id, version)
        :rtype: list
        """
        deps = []
        for imp in self._xml.findall("requires/import"):
            addion_id = imp.attrib["addon"]
            if addion_id not in IGNORE_LIST:
                dep = Dependency(addion_id, imp["version"])
                deps.append(dep)

        return deps

    @utils.CacheProperty
    def valid_type(self, content_type):  # type: (str) -> str
        """All list content that this addon provides e.g. video, audio."""
        if content_type:
            data = self._xml.find("./extension[@point='xbmc.python.pluginsource']/provides")
            if data is not None:
                for provider in data.text.split(" "):
                    if content_type.lower() == provider.strip().lower():
                        return content_type

            # The given content type was not specified in addon.xml
            raise ValueError("content_type '{}' is not one of the specified providers: {}".format(content_type, data))

    def setup_paths(self):
        """Setup library paths."""
        # Append addon library path to sys.path if addon is a module.
        data = self._xml.find("./extension[@point='xbmc.python.module']")
        if data is not None:
            path = os.path.join(self.path, os.path.normpath(data.attrib["library"]))
            sys.path.insert(0, path)
