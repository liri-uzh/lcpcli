"""
The simplest possible parser, which doesn't need to change anything at all
"""

from ._parser import Parser


class JSONParser(Parser):
    def __init__(self):
        super().__init__()

    def parse(self, content):
        return content

    def write(self, content, filepath=None):
        return content

    def combine(self, content):
        return content
