#!/usr/bin/env python
from setuptools import setup as finalize, find_packages
from codecs import open
from glob import glob
import sys
import os

# Setup parameters
setup = {}
classifiers = setup.setdefault("classifiers", [])


def data_files(path, data_dir):
    """
    Walk the package data directory and return a list of paths to the data files.

    :param str path: Path to package.
    :param str data_dir: Path to data directory relative to the package directory.
    """
    datafiles = []
    path = path.rstrip(os.path.sep)
    for root, _, files in os.walk(os.path.join(path, data_dir)):
        root = root.replace(path + os.path.sep, "")
        for filename in files:
            filepath = os.path.join(root, filename)
            datafiles.append(filepath)
    return datafiles


def version_classifiers(vers):
    """
    Create Python Version Classifiers.

    :param list vers: List of python versions as floats.
    """
    data = []
    for ver in vers:
        sub_ver = "Programming Language :: Python :: {}".format(ver)
        data.append(sub_ver)

        main_ver = "Programming Language :: Python :: {}".format(int(ver))
        if main_ver not in data:
            data.append(main_ver)

    return data


def required_versions(vers):
    """
    Create python_requires stirng of supported python versions.

    >>> required_versions([2.7, 3.3, 3.4])
    ">=2.7, !=3.0.*, !=3.1.*, !=3.2.*"

    :param list vers: List of python versions as floats.
    :returns: A string of supported python versions
    :rtype: str
    """
    vers.sort()
    if 2.7 in vers:
        requires = [">=2.7"]
        py3vers = [ver for ver in vers if ver >= 3]
        if py3vers:
            low_ver = py3vers[0]

            start = 3.0
            while start < low_ver:
                requires.append("!={}.*".format(round(start, 1)))
                start += 0.1

        return ", ".join(requires)
    else:
        return ">={}".format(vers[0])


def readme(name="README.rst"):
    """Return the Readme text."""

    if name.endswith(".md"):
        setup["long_description_content_type"] = "text/markdown"

    with open(name, "r", encoding="utf-8") as stream:
        return stream.read()


# ############### Metadata ############### #
setup.update(
    version="0.0.13",
    name="kodi-addon-dev",
    description="Mock Kodi environment for development and testing of Kodi add-on's",
    long_description=readme("README.md"),
    keywords="kodi plugin addon cli",
    author="William Forde",
    author_email="willforde@gmail.com",
    url="https://github.com/willforde/kodi-addondev",
    zip_safe=False
)

# List of supported python versions
py_versions = [2.7, 3.6]


# ############### Dependencies ############### #
setup["install_requires"] = [
    'pytest',
    'requests',
    'appdirs',
    'backports.shutil_get_terminal_size;python_version<"3.3"',
    'typing;python_version<"3.5"',
    'mock;python_version<"3.3"'
]

setup["tests_require"] = [
    'pytest-cov'
]


# ############### Packaging ############### #
setup.update(
    package_dir={'': 'src'},
    packages=find_packages("src"),
    package_data={"kodi_addon_dev": data_files("src/kodi_addon_dev", "data")},
    py_modules=[os.path.splitext(os.path.basename(path))[0] for path in glob("src/*.py")],
    include_package_data=True
)

setup["entry_points"] = points = {"pytest11": ["kodi-addon-dev=kodi_addon_dev.plugin"]}
if sys.version_info >= (3, 0):
    points["console_scripts"] = ["kodi-addon-dev=kodi_addon_dev.__main__:main"]


# ############### Classifiers ############### #
# Full list: https://pypi.python.org/pypi?%3Aaction=list_classifiers

classifiers.extend([
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Natural Language :: English",
    "Topic :: Software Development",
    "Framework :: Pytest"
])

# License
setup["license"] = "MIT License"
classifiers.append("License :: OSI Approved :: MIT License")

# Platforms
setup["platforms"] = "OS Independent"
classifiers.append("Operating System :: OS Independent")

# Python version classifiers
classifiers.extend(version_classifiers(py_versions))


# ############### Finalize ############### #
for required in ("name", "version"):
    if required not in setup:
        raise RuntimeError("missing required metadata: {}".format(required))

finalize(**setup)
