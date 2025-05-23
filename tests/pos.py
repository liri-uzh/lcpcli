import json
import os
import shutil

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def create_corpus():
    shutil.rmtree(TMP_FOLDER)
    os.makedirs(TMP_FOLDER)
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
    print("Corpus created")


create_corpus()
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
