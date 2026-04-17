import json
import os
import shutil
import pytest

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def test_fts_corpus_creation():
    """Test creating a corpus with FTS (Full-Text Search) features."""
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
    os.makedirs(TMP_FOLDER, exist_ok=True)
    c = Corpus(
        "my test corpus", description="This is just a test corpus", authors="Jeremy"
    )
    t1 = c.Token("hello")
    t2 = c.Token("world")
    t3 = c.Token("\\")
    s1 = c.Segment(t1, t2, t3)
    s1.make()
    t3 = c.Token("bye")
    t4 = c.Token("world")
    t5 = c.Token("'")
    s2 = c.Segment(t3, t4, t5)
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
