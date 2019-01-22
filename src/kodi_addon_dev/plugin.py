# Standard Library Imports
import functools
import argparse
import os

# Package imports
from .setup import initializer
from .support import Addon
import xbmc

# Third party imports
import pytest

try:
    from unittest import mock
except ImportError:
    import mock

try:
    # noinspection PyCompatibility
    from collections.abc import MutableMapping
except ImportError:
    from collections import MutableMapping


class RealPath(argparse.Action):
    """
    Custom action to convert given path to a full canonical path,
    eliminating any symbolic links if encountered.
    """
    def __call__(self, _, namespace, value, option_string=None):
        setattr(namespace, self.dest, os.path.realpath(value))


class AppendSplitter(argparse.Action):
    """
    Custom action to split multiple parameters which are
    separated by a comma, and append then to a default list.
    """
    def __call__(self, _, namespace, values, option_string=None):
        items = self.default if isinstance(self.default, list) else []
        items.extend(value.strip() for value in values.split(","))
        setattr(namespace, self.dest, items)


def pytest_addoption(parser):
    """Add command line arguments related to this pluging."""
    group = parser.getgroup("kodi-addondev", "kodi addon testing support")
    group.addoption(
        "--addon-path",
        action=RealPath,
        dest="addon",
        help="Path to the kodi addon being tested.")
    group.addoption(
        "--custom-repos",
        action=AppendSplitter,
        dest="repos",
        help="Comma separated list of custom repo urls.")
    group.addoption(
        "--local-repos",
        action=AppendSplitter,
        dest="local_repos",
        help="Comma separated list of directorys where kodi addons are stored..")


def pytest_configure(config):
    """
    Setup the mock kodi environment after the command line options have
    been parsed and all plugins and initial conftest files been loaded.
    """
    path = config.known_args_namespace.addon
    if path:
        initializer(path, config.known_args_namespace.repos, config.known_args_namespace.local_repos)


def pytest_runtest_call():
    """Clear the kodi session data before every test."""
    xbmc.session.data.clear()


class SettingsMocker(MutableMapping):
    """Mock addon settings and pervent settings from being saved to disk."""
    def __init__(self, request, addon_id=None):
        # Fetch the required addon
        self.addon = addon = xbmc.session.get_addon(addon_id)  # type: Addon

        # Save original object
        self.org_settings = addon.settings.copy()
        self.org_set_setting = addon.set_setting

        # Monkey patch set_settings with dict setitem to pervent saving setting to disk
        addon.set_setting = addon.settings.__setitem__

        request.addfinalizer(self.close)
        self.settings = addon.settings
        self.closed = False

    def __enter__(self):
        return self.settings

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Restore the original objects."""
        if not self.closed:
            self.addon.settings = self.org_settings
            self.addon.set_setting = self.org_set_setting
            self.settings = None
            self.closed = True

    def __setitem__(self, k, v):
        self.settings[k] = v

    def __delitem__(self, k):
        del self.settings[k]

    def __getitem__(self, k):
        return self.settings[k]

    def __iter__(self):
        return iter(self.settings)

    def __len__(self):
        len(self.settings)


############
# Fixtures #
############


@pytest.fixture
def mock_dialog():
    """Mock the xbmcgui Dialog class with a MagicMock object."""
    with mock.patch("xbmcgui.Dialog", autospec=True) as mock_obj:
        yield mock_obj.return_value


@pytest.fixture
def mock_keyboard():
    """Mock the xbmcgui Keyboard class with a MagicMock object."""
    with mock.patch("xbmc.Keyboard", autospec=True) as mock_obj:
        yield mock_obj.return_value


@pytest.fixture
def session_data():
    """Return the kodi session data related to running test."""
    return xbmc.session.data


@pytest.fixture
def mock_settings(request):
    """Return the settings context manager"""
    return functools.partial(SettingsMocker, request)
