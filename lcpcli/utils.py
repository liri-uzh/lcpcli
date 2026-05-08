import diskcache
import json
import os
import re

from datetime import date
from jsonschema import validate
from pathlib import Path


def get_file_from_base(fn: str, files: list[str]) -> str:
    out_fn = next((f for f in files if Path(f).stem.lower() == fn.lower()), None)
    assert out_fn, FileNotFoundError(f"Could not find a file for {fn}")
    return out_fn


def esc(
    value: str | int,
    quote: str = '"',
    double: bool = True,
    escape_backslash: bool = False,
) -> str:
    return (
        str(value)
        .replace("'", "''" if double else "'")
        .replace("\\n", "")
        .replace("\\", "\\\\" if escape_backslash else "\\")
        .replace(quote, quote + quote)
    )


def sorted_dict(d: dict) -> dict:
    ret = {}
    for k in sorted(d):
        v = d[k]
        if isinstance(v, dict):
            v = sorted_dict(v)
        elif isinstance(v, list):
            v = sorted(v)
        ret[k] = v
    return ret


def find_config_file(path: str) -> str:
    parent_dir = os.path.dirname(__file__)
    schema_path = os.path.join(parent_dir, "data", "lcp_corpus_template.json")
    with open(schema_path, "r", encoding="utf-8") as schema_file:
        config_schema = json.loads(schema_file.read())
    config_file_ref: str = ""
    for f in os.listdir(path):
        if not f.endswith(".json"):
            continue
        config_file_ref = os.path.join(path, f)
        with open(os.path.join(path, f), "r") as config_input:
            try:
                config_json = json.loads(config_input.read())
                validate(config_json, config_schema)
                break
            except:
                config_file_ref = ""

    if not config_file_ref:
        raise FileNotFoundError(f"No valid JSON configuration file found in {path}")

    return config_file_ref


def yes_no_input(prompt: str = "Type YES/Y/yes/y or NO/N/no/n: ") -> bool:
    return re.match(r"(no|n)", input(prompt), re.IGNORECASE) is None


class SpillDict:
    max_in_memory_items = 9999999
    overall_size = 0
    reached = False

    def __init__(self):
        self.in_memory = {}
        self.dc = diskcache.Cache()
        self.size = 0

    def __del__(self):
        pass

    def __setitem__(self, key, value):
        if key in self.in_memory:
            self.in_memory[key] = value
            return
        if self.dc and key in self.dc:
            self.dc[key] = value
            return
        if SpillDict.overall_size < SpillDict.max_in_memory_items:
            self.in_memory[key] = value
        else:
            if not SpillDict.reached:
                print("Reached the limit, using disk storage now")
                SpillDict.reached = True
            self.dc[key] = value
        self.size += 1
        SpillDict.overall_size += 1

    def __getitem__(self, key):
        if key in self.in_memory:
            return self.in_memory[key]
        else:
            return self.dc[key]

    def __eq__(self, other):
        if not isinstance(other, SpillDict):
            return False
        return self == other

    def __len__(self):
        return self.size

    def __bool__(self):
        return self.size > 0

    def __contains__(self, key) -> bool:
        return key in self.in_memory or key in self.dc

    def __iter__(self):
        for k in self.in_memory:
            yield k
        for k in self.dc:
            yield k

    def items(self):
        for k in self.in_memory:
            yield (k, self.in_memory[k])
        for k in self.dc:
            yield (k, self.dc[k])

    def setdefault(self, key, value):
        if key not in self.in_memory and key not in self.dc:
            self.__setitem__(key, value)
        return self.__getitem__(key)

    def keys(self):
        for k in self.in_memory:
            yield k
        for k in self.dc:
            yield k

    def values(self):
        for k in self.in_memory:
            yield self.in_memory[k]
        for k in self.dc:
            yield self.dc[k]

    def get(self, key: str, default=None):
        val = default
        try:
            val = self.__getitem__(key)
        except:
            pass
        return val


# Compute left/right from parent only once
class NestedSet:
    def __init__(self, id, label="", cursor=0):
        self.id = id
        self.children = []
        self.parent = None
        self.label = label
        self.cursor_id = cursor
        self.consumed = False

    def compute_anchors(self, left=1):
        self.left = left
        for c in self.children:
            left = c.compute_anchors(left=left + 1)
        self.right = left + 1
        return self.right

    @property
    def all_ids(self):
        ids = [self.id]
        for c in self.children:
            ids += c.all_ids
        return ids

    def add(self, child):
        if child in self.children:
            return
        self.children.append(child)
        child.parent = self


def default_json(name):
    return {
        "meta": {
            "name": name,
            "authors": "Anonymous",
            "date": date.today().strftime("%Y-%m-%d"),
            "revision": 1,
            "corpusDescription": "",
        },
        "firstClass": {"document": "Document", "segment": "Segment", "token": "Token"},
        "layer": {
            "Token": {
                "abstract": False,
                "layerType": "unit",
                "anchoring": {"location": False, "stream": True, "time": False},
            },
            "Segment": {"abstract": False, "layerType": "span", "contains": "Token"},
            "Document": {
                "abstract": False,
                "contains": "Segment",
                "layerType": "span",
            },
        },
    }
