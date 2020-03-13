#!/usr/bin/env python

from setuptools import find_packages
from setuptools import setup

dependencies = [
    "wheel",
    "requests",
    "argparse",
    "cmd2",
    "pygments",
    "regex",
    "python-networkmanager",
    "dbus-python",
]

dependency_links = [
    "https://github.com/calebstewart/python-networkmanager/tarball/master#egg=python-networkmanager"
]

# Setup
setup(
    name="htb",
    version="0.1",
    description="Hack the Box Platform API",
    author="Caleb Stewart",
    url="https://github.com/calebstewart/python-htb",
    packages=find_packages(),
    package_data={"htb": []},
    entry_points={"console_scripts": ["htb=htb.__main__:main"]},
    install_requires=dependencies,
    dependency_links=dependency_links,
)
