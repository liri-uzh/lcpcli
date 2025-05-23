import json
import os
import shutil

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def create_corpus():
    shutil.rmtree(TMP_FOLDER)
    os.makedirs(TMP_FOLDER)
    c = Corpus("my test corpus", document="Book", segment="Sentence", token="Word")
    t1 = c.Word("hello")
    t2 = c.Word("world")
    s1 = c.Sentence(t1, t2).make()
    t3 = c.Word("bye")
    t4 = c.Word("cruel")
    t5 = c.Word("world")
    t6 = c.Word("I")
    t7 = c.Word("quit")
    s2 = c.Sentence(t3, t4, t5, t6, t7).make()
    c.NamedEntity(t4, t5, form="cruel world").make()
    c.Book(s1, s2, title="first document").make()
    c.Book(c.Sentence(original="(empty)"), title="second document").make()
    c.make(TMP_FOLDER)
    print("Corpus created")


create_corpus()
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
