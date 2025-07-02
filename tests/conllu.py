import json
import os
import re
import shutil

from lcpcli.builder import *
from lcpcli.check_files import Checker

TMP_FOLDER = os.path.join(os.path.dirname(__file__), "tmp_data")


def get_obj(misc: str) -> dict:
    return {
        x.split("=")[0].strip(): x.split("=")[1].strip()
        for x in misc.strip().split("|")
        if x and x.split("=")[0].strip() and x.split("=")[1].strip()
    }


def process_sent(c, sent: dict):
    sent["entity"].make()
    for token_props in sent["tokens"].values():
        if not token_props["head"]:
            continue
        deprel_args = {
            "dependent": token_props["entity"],
            "deprel": token_props["deprel"],
        }
        if token_props["head"] != "0":
            deprel_args["head"] = sent["tokens"][token_props["head"]]["entity"]
        c.DepRel(**deprel_args).make()
    for misc, form, mwu in sent["mwu"]:
        misc_obj = get_obj(misc)
        sent["entity"].Mwu(
            *[sent["tokens"][tid]["entity"] for tid in mwu], form=form, misc=misc_obj
        ).make()


def create_corpus(conllu: str):
    shutil.rmtree(TMP_FOLDER)
    os.makedirs(TMP_FOLDER)
    c = Corpus("my test conllu corpus")
    current_doc: dict = {"attributes": {}, "entity": None}
    current_sent: dict = {"attributes": {}, "entity": None, "tokens": {}, "mwu": []}
    for line in conllu.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("# newdoc "):
            attr, val = line[9:].split("=", 2)
            if attr == "id":
                if current_doc["entity"]:
                    current_doc["entity"].make()
                current_doc = {"attributes": {}, "entity": None}
            current_doc["attributes"][attr.strip()] = val.strip()
            continue
        if line.startswith("# sent_id "):
            if current_sent["entity"]:
                process_sent(c, current_sent)
            assert current_doc, RuntimeError(
                "Encountered a new sentence before a new document"
            )
            current_doc["entity"] = c.Document(
                **{
                    x.replace("id", "docid"): y
                    for x, y in current_doc["attributes"].items()
                    if x not in ("start", "end")
                }
            )
            current_sent = {"attributes": {}, "entity": None, "tokens": {}, "mwu": []}
        if m := re.match(r"# ([^=]+)=(.+)$", line):
            if m[1].strip() and m[2].strip():
                current_sent["attributes"][m[1].strip()] = m[2].strip()
            continue
        if not current_sent["entity"]:
            current_sent["entity"] = current_doc["entity"].Segment(
                **{
                    x.replace("sent_id", "sent").replace("text", "original"): y
                    for x, y in current_sent["attributes"].items()
                    if x not in ("start", "end")
                }
            )
        token_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc = [
            "" if x == "_" else x.strip() for x in line.split("\t")
        ]
        if "-" in token_id:
            current_sent["mwu"].append((misc, form, token_id.split("-")))
        else:
            feats_obj = get_obj(feats)
            misc_obj = get_obj(misc)
            kwargs: dict = {}
            if lemma:
                kwargs["lemma"] = lemma
            if upos:
                kwargs["upos"] = upos
            if xpos:
                kwargs["xpos"] = xpos
            if feats_obj:
                kwargs["feats"] = feats_obj
            if misc_obj:
                kwargs["misc"] = misc_obj
            current_sent["tokens"][token_id] = {
                "head": head,
                "deprel": deprel,
                "entity": current_sent["entity"].Token(
                    form,
                    **kwargs,
                ),
            }
    process_sent(c, current_sent)
    current_doc["entity"].make()
    c.make(TMP_FOLDER)
    print("Corpus created")


conllu_str = """# newdoc id = unine15a01m
# newdoc audio = unine15a01m.mp3
# newdoc end = 715.19
# newdoc filename = unine15a01m.xml
# newdoc start = 0.0

# sent_id = a6
# end = 1.04
# speaker = SPK1
# start = 0.71
# text = ben
# who = unine15-001
1	ben	ben	_	ITJ	_	_	_	_	start=0.71|end=1.04

# sent_id = a18
# end = 3.95
# speaker = SPK1
# start = 2.99
# text = ben disons que j'ai pas l'im/
# who = unine15-001
1	ben	ben	_	ITJ	_	_	_	_	start=2.99|end=3.11
2	disons	dire	_	VER	_	_	_	_	agreement=1p|start=3.11|end=3.35
3	que	que	_	CON	_	_	_	_	conjunction=CON|key=MINg|start=3.35|end=3.47
4	j'	je	_	PRO	_	_	_	_	agreement=1s|start=3.47|end=3.55
5	ai	avoir	_	VER	_	_	_	_	agreement=1s|start=3.55|end=3.63
6	pas	pas	_	ADV	_	_	_	_	start=3.63|end=3.75
7	l'	le	_	DET	_	_	_	_	agreement=ms:fs|start=3.75|end=3.83
8	im/	_	_	0	_	_	_	_	filler=FST|start=3.83|end=3.95

# sent_id = a65
# end = 5.68
# speaker = SPK1
# start = 4.22
# text = j'ai pas l'impression déjà d'avoir un accent
# who = unine15-001
1	j'	je	_	PRO	_	_	_	_	agreement=1s|start=4.22|end=4.3
2	ai	avoir	_	VER	_	_	_	_	agreement=1s|start=4.3|end=4.38
3	pas	pas	_	ADV	_	_	_	_	start=4.38|end=4.49
4	l'	le	_	DET	_	_	_	_	agreement=ms:fs|start=4.49|end=4.57
5	impression	impression	_	NOM	_	_	_	_	agreement=fs|start=4.57|end=4.95
6	déjà	déjà	_	ADV	_	_	_	_	start=4.95|end=5.11
7	d'	de	_	CON	_	_	_	_	conjunction=CON|key=MINg|start=5.11|end=5.18
8	avoir	avoir	_	VER	_	_	_	_	start=5.18|end=5.37
9	un	un	_	DET	_	_	_	_	agreement=ms|start=5.37|end=5.45
10	accent	accent	_	NOM	_	_	_	_	agreement=ms|start=5.45|end=5.68

# sent_id = a122
# end = 6.43
# speaker = SPK1
# start = 5.85
# text = moi-même
# who = unine15-001
1-2	moi-même	_	_	_	_	_	_	_	start=5.85|end=6.43|type=PRO:ref
1	moi	moi	_	PRO	_	_	_	_	agreement=1s|start=5.85|end=6.14
2	même	même	_	ADJ	_	_	_	_	agreement=ms:fs|start=6.14|end=6.43

# sent_id = a137
# end = 7.4
# speaker = SPK1
# start = 6.6
# text = du coup euh
# who = unine15-001
1-2	du coup	_	_	_	_	_	_	_	start=6.6|end=7.13|type=ADV
1	du	du	_	PRP	_	_	_	_	agreement=ms|conjunction=MD|key=MAJ|start=6.6|end=6.78
2	coup	coup	_	NOM	_	_	_	_	agreement=ms|conjunction=MD|key=MAJ|start=6.78|end=7.13
3	euh	euh	_	ITJ	_	_	_	_	filler=FIL|key=MAJ|start=7.13|end=7.4

# sent_id = a157
# end = 10.4
# speaker = SPK1
# start = 8.37
# text = c'est aussi ça qui est qui rend difficile
# who = unine15-001
1-2	c'est	_	_	_	_	_	_	_	start=8.37|end=8.66|type=INTROD
1	c'	ce	_	PRO	_	_	_	_	agreement=3ms|conjunction=CON|key=MINg|start=8.37|end=8.48
2	est	être	_	VER	_	_	_	_	agreement=3p|conjunction=CON|key=MINg|start=8.48|end=8.66
3	aussi	aussi	_	ADV	_	_	_	_	start=8.66|end=8.96
4	ça	ça	_	PRO	_	_	_	_	agreement=3ms|start=8.96|end=9.08
5	qui	qui	_	PRO	_	_	_	_	start=9.08|end=9.26
6	est	être	_	VER	_	_	_	_	agreement=3p|start=9.26|end=9.44
7	qui	qui	_	PRO	_	_	_	_	start=9.44|end=9.62
8	rend	rendre	_	VER	_	_	_	_	agreement=3p|start=9.62|end=9.86
9	difficile	difficile	_	ADJ	_	_	_	_	agreement=ms:fs|start=9.86|end=10.4

# sent_id = a207
# end = 16.28
# speaker = SPK1
# start = 11.05
# text = mais on reconnaît quand même euh quand c'est un français qui parle ou quand c'est un neuchâtelois ou alors surtout un belge
# who = unine15-001
1	mais	mais	_	CON	_	_	_	_	conjunction=CON|key=MINg|start=11.05|end=11.26
2	on	on	_	PRO	_	_	_	_	agreement=3s+impers|start=11.26|end=11.36
3	reconnaît	reconnaître	_	VER	_	_	_	_	agreement=3p|start=11.36|end=11.82
4-5	quand même	_	_	_	_	_	_	_	start=11.82|end=12.28|type=ADV
4	quand	quand	_	CON	_	_	_	_	start=11.82|end=12.08
5	même	même	_	ADV	_	_	_	_	start=12.08|end=12.28
6	euh	euh	_	ITJ	_	_	_	_	filler=FIL|start=12.28|end=12.44
7	quand	quand	_	CON	_	_	_	_	conjunction=CON|key=MINg|start=12.44|end=12.69
8-9	c'est	_	_	_	_	_	_	_	start=12.69|end=12.95|type=INTROD
8	c'	ce	_	PRO	_	_	_	_	agreement=3ms|conjunction=CON|key=MINg|start=12.69|end=12.79
9	est	être	_	VER	_	_	_	_	agreement=3p|conjunction=CON|key=MINg|start=12.79|end=12.95
10	un	un	_	DET	_	_	_	_	agreement=ms|start=12.95|end=13.05
11	français	français	_	NOM	_	_	_	_	agreement=ms|start=13.05|end=13.46
12	qui	qui	_	PRO	_	_	_	_	start=13.46|end=13.62
13	parle	parler	_	VER	_	_	_	_	agreement=1s:3s|start=13.62|end=13.87
14	ou	ou	_	CON	_	_	_	_	conjunction=CON|key=MINg|start=13.87|end=13.97
15	quand	quand	_	CON	_	_	_	_	conjunction=CON|key=MINg|start=13.97|end=14.23
16-17	c'est	_	_	_	_	_	_	_	start=14.23|end=14.49|type=INTROD
16	c'	ce	_	PRO	_	_	_	_	agreement=3ms|conjunction=CON|key=MINg|start=14.23|end=14.33
17	est	être	_	VER	_	_	_	_	agreement=3p|conjunction=CON|key=MINg|start=14.33|end=14.49
18	un	un	_	DET	_	_	_	_	agreement=ms|start=14.49|end=14.59
19	neuchâtelois	neuchâtelois	_	NOM	_	_	_	_	start=14.59|end=15.21
20	ou	ou	_	CON	_	_	_	_	conjunction=CON|key=MINg|start=15.21|end=15.31
21	alors	alors	_	ADV	_	_	_	_	start=15.31|end=15.56
22	surtout	surtout	_	ADV	_	_	_	_	start=15.56|end=15.92
23	un	un	_	DET	_	_	_	_	agreement=ms|start=15.92|end=16.03
24	belge	belge	_	ADJ	_	_	_	_	agreement=ms:fs|start=16.03|end=16.28"""


create_corpus(conllu_str)
conf = json.loads(open(os.path.join(TMP_FOLDER, "config.json"), "r").read())
checker = Checker(conf)
checker.run_checks(TMP_FOLDER, full=True, add_zero=False)
