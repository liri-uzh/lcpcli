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
    speakers = {"A": c.Speaker({"name": "A"}), "B": c.Speaker({"name": "B"})}
    s1 = c.Segment(c.Token("hello"), c.Token("world"), speaker=speakers["A"], lang="en")
    s1.set_time(0, 100).make()
    s2 = c.Segment(c.Token("bye"), c.Token("world"), speaker=speakers["B"], lang="en")
    s2.set_time(100, 200).make()
    d1 = c.Movie(s1, s2, name="Foo").set_media("film", "foo.mp4")
    d1.make()
    s3 = c.Segment(c.Token("lorem"), c.Token("ipsum"), speaker=speakers["A"], lang="la")
    s3.set_time(200, 250).make()
    s4 = c.Segment(c.Token("dolor"), c.Token("sit"), speaker=speakers["B"], lang="la")
    s4.set_time(250, 300).make()
    d2 = c.Movie(s3, s4, name="Bar", note="latin").set_media("film", "bar.mp4")
    d2.make()
    c.make(TMP_FOLDER)
    print("Corpus created")


create_corpus()
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
conf["tracks"] = {
    "layers": {"Segment": {"split": ["lang"]}},
    "group_by": ["speaker"],
}
open(os.path.join(TMP_FOLDER, "config.json"), "w").write(json.dumps(conf, indent=True))
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
