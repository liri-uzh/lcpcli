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
    t1 = c.Token("I")
    t2 = c.Token("just")
    t3 = c.Token("shot")
    t4 = c.Token("the")
    t5 = c.Token("best")
    t6 = c.Token("in")
    t7 = c.Token("cinema")
    t8 = c.Token("shot")
    s1 = c.Segment(t1, t2, t3, t4, t5, t6, t7, t8)
    s1.make()
    c.DepRel.make(
        c.DepRel(dependent=t3, udep="root"),
        c.DepRel(head=t3, dependent=t1, udep="nsubj"),
        c.DepRel(head=t3, dependent=t2, udep="advmod"),
        c.DepRel(head=t3, dependent=t6, udep="obj"),
        c.DepRel(head=t6, dependent=t4, udep="detj"),
        c.DepRel(head=t6, dependent=t5, udep="amod"),
        c.DepRel(head=t3, dependent=t8, udep="obl"),
        c.DepRel(head=t8, dependent=t7, udep="case"),
    )
    t9 = c.Token("And")
    t10 = c.Token("then")
    t11 = c.Token("you")
    t12 = c.Token("get")
    t13 = c.Token("into")
    t14 = c.Token("editing")
    t15 = c.Token("and")
    t16 = c.Token("you")
    t17 = c.Token("'re")
    t18 = c.Token("like")
    t19 = c.Token("I")
    t20 = c.Token("just")
    t21 = c.Token("shot")
    t22 = c.Token("the")
    t23 = c.Token("worst")
    t24 = c.Token("shot")
    t25 = c.Token("in")
    t26 = c.Token("cinema")
    s2 = c.Segment(
        t9,
        t10,
        t11,
        t12,
        t13,
        t14,
        t15,
        t16,
        t17,
        t18,
        t19,
        t20,
        t21,
        t22,
        t23,
        t24,
        t25,
        t26,
    )
    s2.make()
    c.DepRel.make(
        c.DepRel(dependent=t12, udep="root"),
        c.DepRel(head=t12, dependent=t9, udep="cc"),
        c.DepRel(head=t12, dependent=t10, udep="advmod"),
        c.DepRel(head=t12, dependent=t11, udep="nsubj"),
        c.DepRel(head=t12, dependent=t14, udep="obl"),
        c.DepRel(head=t14, dependent=t13, udep="case"),
        c.DepRel(head=t12, dependent=t17, udep="conj"),
        c.DepRel(head=t17, dependent=t15, udep="cc"),
        c.DepRel(head=t17, dependent=t16, udep="nsubj"),
        c.DepRel(head=t12, dependent=t21, udep="conj"),
        c.DepRel(head=t21, dependent=t18, udep="discourse"),
        c.DepRel(head=t21, dependent=t19, udep="nsubj"),
        c.DepRel(head=t21, dependent=t20, udep="advmod"),
        c.DepRel(head=t21, dependent=t24, udep="obj"),
        c.DepRel(head=t24, dependent=t22, udep="det"),
        c.DepRel(head=t24, dependent=t23, udep="amod"),
        c.DepRel(head=t21, dependent=t26, udep="obl"),
        c.DepRel(head=t26, dependent=t25, udep="case"),
    )
    d = c.Document(s1, s2, title="only document")
    d.make()
    c.make(TMP_FOLDER)
    print("Corpus created")


create_corpus()
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
