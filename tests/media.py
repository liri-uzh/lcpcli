import json
import os
import shutil

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def create_corpus():
    shutil.rmtree(TMP_FOLDER)
    os.makedirs(TMP_FOLDER)
    c = Corpus("my test corpus", document="Movie")
    s1 = c.Segment(c.Token("hello"), c.Token("world"))
    s1.set_time(0, 100).make()
    s2 = c.Segment(c.Token("bye"), c.Token("world"))
    s2.set_time(100, 200).make()
    d1 = c.Movie(s1, s2, name="Foo").set_media("film", "foo.mp4")
    d1.make()
    s3 = c.Segment(c.Token("lorem"), c.Token("ipsum"))
    s3.set_time(200, 250).make()
    s4 = c.Segment(c.Token("dolor"), c.Token("sit"))
    s4.set_time(250, 300).make()
    d2 = c.Movie(s3, s4, name="Bar", note="latin").set_media("film", "bar.mp4")
    d2.make()
    c.make(TMP_FOLDER)
    print("Corpus created")


create_corpus()
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
