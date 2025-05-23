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
    t1 = c.Token(
        "hello", morph={"gender": "NA", "number": "NA", "mophemes": ["hel", "lo"]}
    )
    t2 = c.Token(
        "world", morph={"gender": "NA", "number": "sg", "mophemes": ["wor", "ld"]}
    )
    s1 = c.Segment(t1, t2)
    s1.make()
    t3 = c.Token("bye", morph={"gender": "NA", "number": "NA", "mophemes": []})
    t4 = c.Token(
        "world", morph={"gender": "NA", "number": "sg", "mophemes": ["wor", "ld"]}
    )
    s2 = c.Segment(t3, t4)
    s2.make()
    d = c.Document(s1, s2, title="only document")
    d.make()
    c.make(TMP_FOLDER)
    print("Corpus created")


create_corpus()
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
