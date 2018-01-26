#!/usr/bin/env python
from setuptools import setup
import os


def data_files():
    datafiles = []
    for root, _, files in os.walk("addondev/data"):
        root = root.replace("addondev/", "")
        for filename in files:
            path = os.path.join(root, filename)
            datafiles.append(path)
    return datafiles


setup(
    name='addondev',
    version='0.0.4',
    description='Launch kodi add-ons from outside kodi.',
    keywords='kodi plugin addon cli',
    classifiers=['Development Status :: 4 - Beta',
                 'Intended Audience :: Developers',
                 'License :: OSI Approved :: MIT License',
                 'Natural Language :: English',
                 'Operating System :: OS Independent',
                 'Programming Language :: Python :: 2.7',
                 'Programming Language :: Python :: 3.6',
                 'Topic :: Software Development'],
    url='https://github.com/willforde/kodi-addondev',
    author='william Forde',
    author_email='willforde@gmail.com',
    license='MIT License',
    install_requires=['requests', 'appdirs', 'backports.shutil_get_terminal_size;python_version<"3.3"'],
    platforms=['OS Independent'],
    packages=['addondev'],
    package_data={'addondev': data_files()},
    entry_points={'console_scripts': ['addondev=addondev.cli:main']},
    extras_require={'dev': ['pytest-cov', 'pytest', 'coverage', 'sphinx', 'backports.shutil_get_terminal_size']},
    include_package_data=True,
    zip_safe=False
)
