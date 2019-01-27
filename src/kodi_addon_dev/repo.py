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
from . import utils
from .support import Addon, Dependency, logger, CACHE_DIR

# Python 2 compatibility
if not utils.PY3:
    from codecs import open

PACKAGE_DIR = os.path.join("packages", CACHE_DIR)
REPOS = ["http://mirrors.kodi.tv/addons/krypton"]
MAX_AGE = 432000


class Repo(object):
    """Check the official kodi repositories for available addons."""

    def __init__(self, cached, remote_repos):
        self.session = requests.session()
        self.cached = cached
        if remote_repos:
            REPOS.extend(remote_repos)

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

    def __contains__(self, addon_id):
        return addon_id in self.db

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
        for addon in self.cached.values():
            if addon.id not in self:
                # We have a cached addon that no longer exists in the repo
                warnings.warn("Cached Addon '{}' no longer available on kodi repo".format(addon.id))

            elif addon.version < self.db[addon.id][1].version:
                self.download(addon)

        # Create update-check file
        # with current timestamp
        timestamp = time.time()
        with open(self.check_file, "w", encoding="utf8") as stream:
            json.dump(timestamp, stream)

    def download(self, dep):  # type: (Union[str, Dependency, Addon]) -> Addon
        if isinstance(dep, str):
            try:
                dep = self.db[dep]
            except KeyError:
                raise KeyError("{} not found on remote repo".format(dep))

        if dep.id not in self:
            raise KeyError("{} not found on remote repo".format(dep))
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
        self.cached[addon.id] = addon
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


class LocalRepo(object):
    def __getstate__(self):
        state = self.__dict__.copy()
        state["repo"] = None
        return state

    def __init__(self, local_repos, remote_repos, addon=None):  # type: (List, List, Addon) -> None
        """Retrun List of already download addons."""
        build_in = os.path.join(os.path.dirname(__file__), "data")
        self.cached = dict(self._find_addons(build_in, CACHE_DIR))
        self.local = dict(self._find_addons(*local_repos))
        self.repo = Repo(self.cached, remote_repos)
        if addon:
            self.local[addon.id] = addon.preload()

    def __contains__(self, addon_id):  # type: (str) -> bool
        return addon_id in self.cached or addon_id in self.local

    def __getitem__(self, addon_id):  # type: (str) -> Addon
        """Return the addon from local repo."""
        if addon_id in self.local:
            return self.local[addon_id]
        else:
            return self.cached[addon_id]

    def load_dependencies(self, addon):  # type: (Addon) -> List
        """Process all dependencies for givin addon and preload addon data."""
        return list(self._process_dependencies(addon.dependencies))

    def request_addon(self, addon_id):  # type: (str) -> Addon
        """Return addon from local repo if available else download from remote repo."""
        try:
            return self[addon_id]
        except KeyError:
            if self.repo and addon_id in self.repo:
                addon = self.repo.download(addon_id)
                self._process_dependencies(addon.dependencies)
                return addon.preload()
            else:
                raise KeyError("{} not found".format(addon_id))

    @staticmethod
    def _find_addons(*paths):  # type: (str) -> Iterator[Tuple[str, Addon]]
        """
        Search givin paths for kodi addons.
        Returning a tuple consisting of addon id and Addon object.
        """
        for addons_dir in paths:
            for filename in os.listdir(addons_dir):
                path = os.path.join(addons_dir, filename, "addon.xml")
                if os.path.exists(path):
                    addon = Addon.from_file(path)
                    yield addon.id, addon

    def _process_dependencies(self, dependencies):  # type: (List[Dependency]) -> Iterator[Addon]
        """
        Process the list of requred dependencies,
        downloading any missing dependencies.
        """
        dep = Dependency("resource.language.en_gb", "1.0.0", False)
        dependencies.append(dep)

        for dep in dependencies:
            # Download dependency if not already downloaded
            if dep.id not in self or dep.version > self[dep.id].version:
                addon = self.repo.download(dep)
            else:
                addon = self[dep.id]

            # Check if the dependency has dependencies
            for extra_dep in addon.dependencies:
                if extra_dep not in dependencies:
                    dependencies.append(extra_dep)

            # Preload addon data
            addon.preload()
            yield addon.id
