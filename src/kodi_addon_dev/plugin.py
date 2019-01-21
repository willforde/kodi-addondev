# Standard Library Imports
import argparse
import os

# Package imports
from .setup import initializer
import xbmc

# Third party imports
import pytest
try:
    from unittest import mock
except ImportError:
    import mock


class RealPath(argparse.Action):
    """
    Custom action to convert given path to a full canonical path,
    eliminating any symbolic links if encountered.
    """
    def __call__(self, _, namespace, value, option_string=None):
        setattr(namespace, self.dest, os.path.realpath(value))


def pytest_addoption(parser):
    """Add command line arguments related to this pluging."""
    group = parser.getgroup("kodi-addondev", "kodi addon testing support")
    group.addoption(
        "--addon-path",
        action=RealPath,
        dest="addon",
        help="Path to the kodi addon being tested.")
    group.addoption(
        "--custom-repo",
        action="store",
        dest="repos",
        help="Comma separated list of custom repo urls.")


def pytest_configure(config):
    """
    Setup the mock kodi environment after the command line options have
    been parsed and all plugins and initial conftest files been loaded.
    """
    path = config.known_args_namespace.addon
    if path:
        _repos = config.known_args_namespace.repos
        repos = [repo.strip() for repo in _repos.split(",")] if _repos else None
        initializer(path, repos)


def pytest_runtest_call():
    """Clear the kodi session data before every test."""
    xbmc.session.data.clear()


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
