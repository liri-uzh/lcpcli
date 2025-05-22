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
    s1 = c.Sentence(t1, t2, original="hello world", keywords=["positive", "greetings"])
    s1.unsure = False
    s1.make()
    s2 = c.Sentence(
        original="bye world", keywords=["negative", "greetings"], unsure=True
    )
    t3 = c.Word("bye")
    s2.add(t3)
    t3.make()
    comm = c.Comment(value="pause")
    comm.set_char(c._char_counter, c._char_counter + 1)
    c._char_counter += 1
    t4 = c.Word("world")
    s2.add(t4)
    s2.make()
    d1 = c.Book(s1, s2, title="first document")
    d1.make()
    d2 = c.Book(c.Sentence(original=""))
    d2.make()
    c.make(TMP_FOLDER)
    print("Corpus created")


create_corpus()
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
