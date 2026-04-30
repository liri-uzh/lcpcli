import json
import os
import shutil
import pytest
import resource
from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def test_clearing():
    """Test clearing child layers for memory optimization."""
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
    os.makedirs(TMP_FOLDER, exist_ok=True)
    c = Corpus(
        "my test corpus", description="This is just a test corpus", authors="Jeremy"
    )
    globs = [c.Speaker({"name": "Jane Doe"}), c.Speaker({"name": "John Doe"})]
    for nd in range(10):
        d = c.Document(name=f"Document {nd}")
        for np in range(20):
            p = d.Paragraph(name=f"Paragraph {np}", speaker=globs[np % 2])
            for ns in range(30):
                tokens = []
                for nt in range(40):
                    tokens.append(c.Token(f"Form {nt}", pos="NN"))
                s = p.Segment(*tokens, name=f"Segment {ns}")
                s.make(clear=True)
                del s
            p.make(clear=True)
            del p
            print(
                f"[PAR] Current memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}"
            )
        d.make(clear=True)
        del d
        print(
            f"[DOC] Current memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}"
        )
    c.make(TMP_FOLDER)
    # Validate the generated files
    conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
    checker = Checker(conf)
    checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
    # Clean up
    shutil.rmtree(TMP_FOLDER, ignore_errors=True)
