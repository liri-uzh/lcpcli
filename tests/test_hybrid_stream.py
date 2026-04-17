import json
import os
import shutil
import pytest

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def test_hybrid_stream_corpus_creation():
    """Test creating a corpus with hybrid stream features."""
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
    os.makedirs(TMP_FOLDER, exist_ok=True)
    c = Corpus("my test corpus", document="Book", segment="Sentence", token="Word")
    t1 = c.Word("hello")
    t2 = c.Word("world")
    s1 = c.Sentence(t1, t2, original="hello world", keywords=["positive", "greetings"])
    s1.unsure = False
    s1.make()
    s2 = c.Sentence(
        c.Word("bye"),
        c.Comment(value="pause"),
        c.Word("world"),
        original="bye world",
        keywords=["negative", "greetings"],
        unsure=True,
    )
    s2.make()
    d1 = c.Book(s1, s2, title="first document")
    d1.make()
    d2 = c.Book(c.Sentence(original=""))
    d2.make()
    c.make(TMP_FOLDER)
    
    # Validate the generated files
    conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
    checker = Checker(conf)
    checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
    
    # Clean up
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
