import os

from setuptools import setup

def read(fname):
    """
    Helper to read README
    """
    return open(os.path.join(os.path.dirname(__file__), fname)).read().strip()


setup(
    name="lcpcli",
    version="0.0.1",
    description="CLI tool combining LCP Upload and LCP Corpert",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    url="",
    author="Jeremy Zehr and Jonathan Schaber",
    include_package_data=False,
    zip_safe=True,
    # packages=["lcpcli","lcp-upload","corpert"],
    scripts=["bin/lcpcli"],
    author_email="jeremy.zehr@uzh.ch",
    # license="MIT",
    # keywords=["corpus", "linguistics", "corpora", "conll", "tei", "vert"],
    install_requires=[],
)