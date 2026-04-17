import json
import os
import shutil
import pytest

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")

# global attributes need to be created first, then they can be referenced


def test_glob_attr_corpus_creation():
    """Test creating a corpus with global attributes."""
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
    os.makedirs(TMP_FOLDER, exist_ok=True)
    c = Corpus("my test corpus")
    p1 = c.Person(
        {
            "firstname": "Jane",
            "lastname": "Doe",
            "age": "35",
            "gender": "f",
        }
    )
    p2 = c.Person(
        {
            "firstname": "John",
            "lastname": "Doe",
            "age": "35",
            "gender": "m",
        }
    )
    t1 = c.Token("hello")
    t2 = c.Token("world")
    s1 = c.Segment(t1, t2, speaker=p1)
    s1.make()
    t3 = c.Token("bye")
    t4 = c.Token("world")
    s2 = c.Segment(t3, t4, speaker=p2)
    s2.make()
    d = c.Document(s1, s2, title="only document")
    d.make()
    c.make(TMP_FOLDER)
    
    # Validate the generated files
    conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
    checker = Checker(conf)
    checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
    
    # Clean up
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
