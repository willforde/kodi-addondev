[![Codacy Badge](https://api.codacy.com/project/badge/Grade/42ba90f33ff64fc7a9c9e3bffebefe0a)](https://www.codacy.com/app/willforde/kodi-addondev?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=willforde/kodi-addondev&amp;utm_campaign=Badge_Grade)

# Kodi-Addon-Dev:
kodi-addon-dev is a development tool for developing, testing and executing kodi addons.
This is achieved by creating a mock Kodi environment without the need for kodi to be installed.
Now that Kodi is not required, development can be contained within the development environment.
Allowing for the use of the debug mode in programs like PyCharm and Eclipse.

Testing is achieved with the help of PyTest, a testing framework for creating easy to write tests.
kodi-addon-dev is setup as a pytest plugin and when called, it will find and execute all your addon tests.

Integration with online testing services like "travis-ci.org" and "coveralls.io" is now possible and easy.
The use of "Tox" for testing with python 2.7 and 3.6 is also possible and recommended.

## Installation
To install kodi-addon-dev, simply use pip:
``` {.sourceCode .bash}
$ pip install kodi-addon-dev
```

## Documentation
To execute addon, call:
```{.sourceCode .bash}
$ python -m kodi-addon-dev PATH_TO_ADDON_DIR
=========================================================
plugin://plugin.video.metalvideo/
=========================================================
 0. + Recent Videos            Listitem({'path': {'id': 'plugin.video...
 1. + Top 50 Videos            Listitem({'path': {'id': 'plugin.video...
 2. + Being watched right now  Listitem({'path': {'id': 'plugin.video...
...
```

To test you addon with PyTest:
```{.sourceCode .bash}
$ pytest --addon-path PATH_TO_ADDON_DIR
===================== test session starts ==========================
platform linux -- Python 3.7.2, pytest-4.2.1, py-1.7.0, pluggy-0.8.1
rootdir: /home/willforde/code/kodi/plugin.video.metalvideo, inifile:
plugins: kodi-addon-dev-0.0.13
collected 16 items                                                                                     

tests/test_addon.py ................                         [100%]
===================== 16 passed in 17.26 seconds ====================
```

The full documentation on how to use this module is available over at read the docs.
http://readthedocs.org/projects/kodi-addon-dev

## TODO
* Add support to create a base addon using a codequick template.
* Add support for 'xbmc.service' plugins
* Do a lot more testing with other kodi addons.

## Note
There are still some rough edges, especially with the XBMC modules.
But with a bit of help and lots of testing, all problems should be solvable.
