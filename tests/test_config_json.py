import json
import os
import shutil
import pytest

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def test_config_json():
    """Test creating a corpus with multiple contained entities."""
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
    os.makedirs(TMP_FOLDER, exist_ok=True)

    config = _get_config()

    c = Corpus(
        config["meta"]["name"],
        document=config["firstClass"]["document"],
        segment=config["firstClass"]["segment"],
        token=config["firstClass"]["token"],
        authors=config["meta"]["authors"],
        description=config["meta"]["corpusDescription"],
        date=config["meta"]["date"],
        revision=config["meta"]["revision"],
        url=config["meta"]["url"],
    )
    speakers = {"A": c.Speaker({"name": "A"}), "B": c.Speaker({"name": "B"})}
    t1 = c.Word("hello")
    t2 = c.Word("world")
    s1 = c.Sentence(t1, t2, speaker=speakers["A"], lang="en").make()
    t3 = c.Word("bye")
    t4 = c.Word("cruel")
    t5 = c.Word("world")
    t6 = c.Word("I")
    t7 = c.Word("quit")
    s2 = c.Sentence(t3, t4, t5, t6, t7, speaker=speakers["B"], lang="la").make()
    c.NamedEntity(t4, t5, form="cruel world").make()
    c.Book(s1, s2, title="first document").set_media("film", "foo.mp4").make()
    c.Book(
        c.Sentence(original="(empty)", speaker=speakers["B"], lang="en"),
        title="second document",
    ).set_media("film", "bar.mp4").make()
    c.make(TMP_FOLDER)

    # Validate the generated files
    conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
    checker = Checker(conf)
    checker.run_checks(TMP_FOLDER, full=True, add_zero=False)

    assert conf == config, ValueError("Invalid output configuration file")

    # Clean up
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)


def _get_config():
    return {
        "meta": {
            "name": "my test corpus",
            "authors": "Jane Doe",
            "corpusDescription": "A super test corpus",
            "date": "January 1, 1970",
            "url": "http://localhost:8080/",
            "revision": 2,
            "mediaSlots": {"film": {"mediaType": "video", "isOptional": False}},
        },
        "firstClass": {"token": "Word", "segment": "Sentence", "document": "Book"},
        "layer": {
            "Word": {
                "anchoring": {"stream": True, "time": False, "location": False},
                "layerType": "unit",
                "attributes": {"form": {"type": "text", "nullable": False}},
            },
            "Sentence": {
                "anchoring": {"stream": True, "time": False, "location": False},
                "layerType": "span",
                "attributes": {
                    "speaker": {"ref": "speaker"},
                    "lang": {
                        "type": "categorical",
                        "nullable": False,
                        "values": ["en", "la"],
                    },
                    "original": {
                        "type": "categorical",
                        "nullable": True,
                        "values": ["(empty)"],
                    },
                },
                "contains": "Word",
            },
            "NamedEntity": {
                "anchoring": {"stream": True, "time": False, "location": False},
                "layerType": "span",
                "attributes": {
                    "form": {
                        "type": "categorical",
                        "nullable": False,
                        "values": ["cruel world"],
                    }
                },
                "contains": "Word",
            },
            "Book": {
                "anchoring": {"stream": True, "time": False, "location": False},
                "layerType": "span",
                "attributes": {
                    "title": {
                        "type": "categorical",
                        "nullable": False,
                        "values": ["first document", "second document"],
                    }
                },
                "contains": "Sentence",
            },
        },
        "globalAttributes": {
            "speaker": {"type": "dict", "keys": {"name": {"type": "text"}}}
        },
    }
