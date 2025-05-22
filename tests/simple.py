from lcpcli.builder import *


def run_test():
    c = Corpus("my test corpus")
    t1 = c.Token("hello")
    t2 = c.Token("world")
    s1 = c.Segment(t1, t2, original="hello world", keywords=["positive", "greetings"])
    s1.make()
    t3 = c.Token("bye")
    t4 = c.Token("world")
    s2 = c.Segment(
        t3, t4, original="bye world", keywords=["negative", "greetings"], unsure=True
    )
    s2.make()
    d = c.Document(s1, s2, title="first document")
    d.make()
    c.make("/home/jeremy/lcpcli_test/builder")


run_test()
