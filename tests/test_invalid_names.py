import json
import os
import shutil
import pytest

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def test_invalid_names_corpus_creation():
    """Test creating a corpus with invalid names."""
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
    os.makedirs(TMP_FOLDER, exist_ok=True)
    c = Corpus(
        "my test corpus", description="This is just a test corpus", authors="Jeremy"
    )
    t1 = c.Token("hello")
    t2 = c.Token("world")
    s1 = c.Segment(t1, t2, speaker=c.Speaker({"age": 36}))
    s1.make()
    t3 = c.Token("bye")
    t4 = c.Token("world")
    with pytest.raises(AssertionError):
        # Attempt to pass an attribute name that contains a space character
        s2 = c.Segment(t3, t4, speaker=c.Speaker({"age": 36, "full name": "Foo Bar"}))
    s2 = c.Segment(t3, t4, speaker=c.Speaker({"age": 36, "fullName": "Foo Bar"}))
    s2.make()
    with pytest.raises(AssertionError):
        # Attempt to pass an attribute name that starts with an uppercase
        d = c.Document(s1, s2, Title="only document")
    d = c.Document(s1, s2, title="only document")
    d.make()
    c.make(TMP_FOLDER)

    # Validate the generated files
    conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
    checker = Checker(conf)
    checker.run_checks(TMP_FOLDER, full=True, add_zero=False)

    # Clean up
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
