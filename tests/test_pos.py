import json
import os
import shutil
import pytest

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def test_pos_corpus_creation():
    """Test creating a corpus with part-of-speech tags."""
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
    os.makedirs(TMP_FOLDER, exist_ok=True)
    c = Corpus("my test corpus")
    c.Document(
        c.Segment(
            c.Token("The", lemma="the", upos="DET", xpos="DT"),
            c.Token("red", lemma="red", upos="ADJ", xpos="JJ"),
            c.Token("fox", lemma="fox", upos="NOUN", xpos="NN"),
            c.Token("jumps", lemma="jump", upos="VERB", xpos="VBP"),
        )
    ).make()
    c.make(TMP_FOLDER, is_global={"Token": ["upos"]})
    
    # Validate the generated files
    conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
    checker = Checker(conf)
    checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
    
    # Clean up
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
