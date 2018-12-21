# Standard Library Imports
from typing import List, Dict, Iterator, Union
import warnings
import zipfile
import shutil
import time
import json
import os

# Third party imports
import requests

# Package imports
from addondev import support2, utils

# Python 2 compatibility
if not utils.PY3:
    from codecs import open

CACHE_DIR = support2.KODI_PATHS["addons"]
PACKAGE_DIR = support2.KODI_PATHS["packages"]
KODI_REPO = "krypton"
MAX_AGE = 432000


class Repo(object):
    """Check the official kodi repositories for available addons."""
    repo_url = "http://mirrors.kodi.tv/addons/{}/{}".format(KODI_REPO, "{}")

    def __init__(self):
        self.session = requests.session()

        # Check if an update is scheduled
        self.check_file = os.path.join(CACHE_DIR, u"update_check")
        if self.update_required():
            support2.logger.info("Checking for updates...")
            self.update()

    @utils.CacheProperty
    def db(self):  # type: () -> Dict[str, support2.Addon]
        """Fetch list of all addons available on the official kodi repository."""
        support2.logger.info("Communicating with kodi's official repository: Please wait.")

        # Parse the full list of available addon
        url = self.repo_url.format("addons.xml")
        resp = self.session.get(url)
        addon_xml = support2.ETree.fromstring(resp.content)

        addons = {}
        for node in addon_xml.iterfind("addon"):
            addon = support2.Addon(node)
            addons[addon.id] = addon

        # Returns a dict of addons with the addon id as key
        return addons

    def update_required(self):  # type: () -> bool
        """Return True if its time to update."""
        if os.path.exists(self.check_file):
            with open(self.check_file, "r") as stream:
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

            elif addon.version < self.db[addon.id].version:
                self.download(addon)

        # Create update-check file
        # with current timestamp
        timestamp = time.time()
        with open(self.check_file, "w") as stream:
            json.dump(stream, timestamp)

    def download(self, dep):  # type: (Union[support2.Dependency, support2.Addon]) -> support2.Addon
        if dep.id not in self.db:
            raise ValueError("Addon '{}' is not available on kodi repo".format(dep.id))
        else:
            addon = self.db[dep.id]

        # Warn user if we are downloading an older
        # version than what is required
        if addon.version < dep.version:
            warnings.warn("required version is greater than whats available: {} < {}"
                          .format(addon.version, dep.version), RuntimeWarning)

        filename = u"{}-{}.zip".format(addon.id, addon.version)
        filepath = os.path.join(PACKAGE_DIR, filename)
        support2.logger.info("Downloading: '{}'".format(filename.encode("utf8")))

        # Remove old zipfile before download
        self.cleanup(addon.id)

        # Remove the old addon directory if exists
        addon_dir = os.path.join(CACHE_DIR, addon.id)
        if os.path.exists(addon_dir):
            shutil.rmtree(addon_dir)

        # Request the addon zipfile from server
        url_part = "{0}/{1}".format(addon.id, filename)
        url = self.repo_url.format(url_part)
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

        self.extract_zip(filename)
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
                filepath = os.path.join(PACKAGE_DIR, addon_id)
                os.remove(filepath)


def cached_addons():  # type: () -> Iterator[support2.Addon]
    """Retrun List of already download addons."""
    for filename in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, filename, "addon.xml")
        if os.path.exists(path):
            yield support2.Addon.from_file(path)


def process_dependencies(dependencies):  # type: (List[support2.Dependency]) -> Iterator[support2.Addon]
    """Process the list of requred dependencies, downloading any missing dependencies."""
    cached = {addon.id: addon for addon in cached_addons()}
    repo = Repo()

    for dep in dependencies:
        # Download dependency if not already downloaded
        if dep.id not in cached or dep.version > cached[dep.id].version:
            addon = repo.download(dep)
        else:
            addon = cached[dep.id]

        addon.setup_paths()
        # Check if the dependency has dependencies
        for extra_dep in addon.dependencies:
            if extra_dep not in dependencies:
                dependencies.append(extra_dep)

        yield addon
