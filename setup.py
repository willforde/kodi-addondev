#!/usr/bin/env python
from setuptools import setup, find_packages
from glob import glob
import os


def data_files():
    datafiles = []
    for root, _, files in os.walk("src/kodi_addon_dev/data"):
        root = root.replace("src/kodi_addon_dev/", "")
        for filename in files:
            path = os.path.join(root, filename)
            datafiles.append(path)
    return datafiles


setup(
    name='kodi-addon-dev',
    version='0.0.12',
    description="Mock Kodi environment for development and testing of Kodi add-on's",
    keywords='kodi plugin addon cli',
    classifiers=['Development Status :: 4 - Beta',
                 'Intended Audience :: Developers',
                 'License :: OSI Approved :: MIT License',
                 'Natural Language :: English',
                 'Operating System :: OS Independent',
                 'Programming Language :: Python :: 2'
                 'Programming Language :: Python :: 2.7',
                 'Programming Language :: Python :: 3'
                 'Programming Language :: Python :: 3.6',
                 'Topic :: Software Development',
                 'Framework :: Pytest'],
    url='https://github.com/willforde/kodi-addondev',
    author='William Forde',
    author_email='willforde@gmail.com',
    license='MIT License',
    install_requires=['pytest', 'requests', 'appdirs',
                      'backports.shutil_get_terminal_size;python_version<"3.3"',
                      'typing;python_version<"3.5"',
                      'mock;python_version<"3.3"'],
    platforms=['OS Independent'],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    package_data={'kodi_addon_dev': data_files()},
    py_modules=[os.path.splitext(os.path.basename(path))[0] for path in glob('src/*.py')],
    entry_points={'console_scripts': ['kodi-addon-dev=kodi_addon_dev.cli:main'],
                  'pytest11': ['kodi-addon-dev=kodi_addon_dev.plugin']},
    extras_require={'dev': ['pytest-cov']},
    include_package_data=True,
    zip_safe=False
)
