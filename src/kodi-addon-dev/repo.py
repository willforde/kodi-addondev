# Standard Library Imports
from typing import List, Dict, Iterator, Union, Tuple
import xml.etree.ElementTree as ETree
import warnings
import zipfile
import shutil
import time
import json
import os

# Third party imports
import requests

# Package imports
from addondev import utils
from addondev.support import Addon, Dependency, logger, CACHE_DIR

# Python 2 compatibility
if not utils.PY3:
    from codecs import open

PACKAGE_DIR = os.path.join("packages", CACHE_DIR)
REPOS = ["http://mirrors.kodi.tv/addons/krypton"]
MAX_AGE = 432000


class Repo(object):
    """Check the official kodi repositories for available addons."""

    def __init__(self):
        self.session = requests.session()

        # Check if an update is scheduled
        self.check_file = os.path.join(CACHE_DIR, u"update_check")
        if self.update_required():
            logger.info("Checking for updates...")
            self.update()

    @utils.CacheProperty
    def db(self):  # type: () -> Dict[str, Tuple[str, Addon]]
        """Fetch list of all addons available on the official kodi repository."""
        logger.info("Communicating with kodi's official repository: Please wait.")

        addons = {}
        for repo in REPOS:
            # Parse the full list of available addons
            url = "{}/{}".format(repo.strip("/"), "addons.xml")
            resp = self.session.get(url)
            addon_xml = ETree.fromstring(resp.content)
            for node in addon_xml.iterfind("addon"):
                addon = Addon(node)
                addons[addon.id] = (repo, addon)

        # Returns a dict of addons with the addon id as key
        return addons

    def update_required(self):  # type: () -> bool
        """Return True if its time to update."""
        if os.path.exists(self.check_file):
            with open(self.check_file, "r", encoding="utf8") as stream:
                timestamp = json.load(stream)
            return timestamp + MAX_AGE < time.time()
        else:
            # Default to True when the check file is missing
            return True

    def update(self):
        """Check if any cached addon need updating."""
        for addon in cached_addons():
            if addon.id not in self.db:
                # We have a cached addon that no longer exists in the repo
                warnings.warn("Cached Addon '{}' no longer available on kodi repo".format(addon.id))

            elif addon.version < self.db[addon.id][1].version:
                self.download(addon)

        # Create update-check file
        # with current timestamp
        timestamp = time.time()
        with open(self.check_file, "w", encoding="utf8") as stream:
            json.dump(timestamp, stream)

    def download(self, dep):  # type: (Union[Dependency, Addon]) -> Addon
        if dep.id not in self.db:
            raise ValueError("Addon '{}' is not available on kodi repo".format(dep.id))
        else:
            repo, addon = self.db[dep.id]

        # Warn user if we are downloading an older
        # version than what is required
        if addon.version < dep.version:
            warnings.warn("required version is greater than whats available: {} < {}"
                          .format(addon.version, dep.version), RuntimeWarning)

        filename = u"{}-{}.zip".format(addon.id, addon.version)
        filepath = os.path.join(PACKAGE_DIR, filename)
        if os.path.exists(filepath):
            logger.info("Using cached package: '{}'".format(filename))
        else:
            logger.info("Downloading: '{}'".format(filename))
            # Remove old zipfiles before download, if any
            self.cleanup(addon.id)

            # Request the addon zipfile from server
            url_part = "{0}/{1}".format(addon.id, filename)
            url = "{}/{}".format(repo, url_part)
            resp = self.session.get(url)

            # Read and save contents of zipfile to package directory
            try:
                with open(filepath, "wb") as stream:
                    for chunk in resp.iter_content(decode_unicode=False):
                        stream.write(chunk)

            except (OSError, IOError) as e:
                self.cleanup(addon.id)
                raise e

            finally:
                resp.close()

        # Remove the old addon directory if exists
        addon_dir = os.path.join(CACHE_DIR, addon.id)
        if os.path.exists(addon_dir):
            shutil.rmtree(addon_dir)

        self.extract_zip(filepath)
        addon.path = addon_dir
        return addon

    @staticmethod
    def extract_zip(src):  # type: (str) -> None
        """Extract all content of zipfile to addon directoy."""
        zipobj = zipfile.ZipFile(src)
        zipobj.extractall(CACHE_DIR)

    @staticmethod
    def cleanup(addon_id):  # type: (str) -> None
        """Remove all packages related to given addon id."""
        for filename in os.listdir(PACKAGE_DIR):
            if filename.startswith(addon_id):
                filepath = os.path.join(PACKAGE_DIR, filename)
                os.remove(filepath)


def cached_addons():  # type: () -> Iterator[Addon]
    """Retrun List of already download addons."""
    builtin_cache = os.path.join(os.path.dirname(__file__), "data")
    for addons_dir in (builtin_cache, CACHE_DIR):
        for filename in os.listdir(addons_dir):
            path = os.path.join(addons_dir, filename, "addon.xml")
            if os.path.exists(path):
                yield Addon.from_file(path)


def process_dependencies(dependencies):  # type: (List[Dependency]) -> Iterator[Addon]
    """Process the list of requred dependencies, downloading any missing dependencies."""
    cached = {addon.id: addon for addon in cached_addons()}
    repo = Repo()

    # Inject resource.language.en_gb requirement Kodi localized strings
    dep = Dependency("resource.language.en_gb", "1.0.0")
    dependencies.append(dep)

    for dep in dependencies:
        logger.info("Processing Dependency: %s", dep.id)
        # Download dependency if not already downloaded
        if dep.id not in cached or dep.version > cached[dep.id].version:
            addon = repo.download(dep)
        else:
            addon = cached[dep.id]

        # Check if the dependency has dependencies
        for extra_dep in addon.dependencies:
            if extra_dep not in dependencies:
                dependencies.append(extra_dep)

        yield addon
