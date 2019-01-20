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
    group = parser.getgroup("kodi-addondev", "kodi addon testing support")
    group.addoption(
        "--addon-path",
        action=RealPath,
        dest="addonpath",
        help="Path to the kodi addon to test.")


@pytest.mark.trylast
def pytest_load_initial_conftests(early_config, *_):
    path = early_config.known_args_namespace.addonpath
    if path:
        initializer(path)


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


@pytest.fixture(autouse=True)
def clean_session(request):
    """Clear the kodi session data before every test."""
    print(request.config.option.addonpath)
    xbmc.session.data.clear()
