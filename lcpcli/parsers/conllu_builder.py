import os
import re

from collections.abc import Iterable, Iterator
from pathlib import Path
from lcpcli.builder import *

CONLLU_COLUMNS = (
    "ID",
    "FORM",
    "LEMMA",
    "UPOS",
    "XPOS",
    "FEATS",
    "HEAD",
    "DEPREL",
    "DEPS",
    "MISC",
)


class LayerProxy:
    dummy_corpus = Corpus("dummy")

    def __init__(self):
        self.attributes = {}
        self.entity: Layer = Layer("dummy", LayerProxy.dummy_corpus)
        self.assigned = False

    def assign_entity(self, layer: Layer):
        self.entity = layer
        self.assigned = True

    def set_attribute(self, name: str, value: Any):
        val = value
        if isinstance(value, str):
            val = value.strip()
            if val.isdigit():
                val = int(val)
            elif val.replace(".", "", 1).isdigit():
                val = float(val)
        self.attributes[name.strip()] = val


class TokenProxy(LayerProxy):
    def __init__(self):
        super().__init__()
        self.head: str = ""
        self.deprel: str = ""


class SentenceProxy(LayerProxy):
    def __init__(self):
        super().__init__()
        self.mwu: list[tuple[str, str, list]] = []
        self.tokens: dict[str, TokenProxy] = {}


def get_obj(misc: str) -> dict:
    """Converts a string like k=v|x=y into a dict like {k:v,x:y}"""
    return {
        x.split("=")[0].strip(): x.split("=")[1].strip()
        for x in misc.strip().split("|")
        if x and x.split("=")[0].strip() and x.split("=")[1].strip()
    }


def process_sent(c, sent: SentenceProxy):
    """Takes a sentence object and generates its tokens + dependencies"""
    if not sent.assigned:
        return
    sent.entity.make()
    sent_deps = []
    # Dependencies are special: you store them and make them all at once
    # in order to optimize processing.
    # This allows one to handle cross-segment dependencies (not the case here though)
    for token_props in sent.tokens.values():
        if not token_props.head:
            continue
        deprel_args = {
            "dependent": token_props.entity,
            "deprel": token_props.deprel,
        }
        if token_props.head != "0":
            deprel_args["head"] = sent.tokens[token_props.head].entity
        sent_deps.append(c.DepRel(**deprel_args))
    c.DepRel.make(*sent_deps)
    for misc, form, mwu in sent.mwu:
        misc_obj = get_obj(misc)
        sent.entity.Mwu(
            *[sent.tokens[tid].entity for tid in mwu], form=form, misc=misc_obj
        ).make()


def create_corpus(input: Iterable[str], corpus_name: str = "Untitled corpus"):
    c = Corpus(corpus_name)
    column_names: list[str] = [x.strip().lower() for x in CONLLU_COLUMNS]
    current_doc: LayerProxy = LayerProxy()
    current_par: LayerProxy = LayerProxy()
    current_sent: SentenceProxy = SentenceProxy()
    comment_for: str = "sentence"
    for line in input:
        # lines starting with 0 is not valid CONLLU syntax but we'll allow it
        token_line = line.startswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"))
        if not token_line and current_sent.assigned and current_sent.tokens:
            process_sent(c, current_sent)
            current_par = LayerProxy()
            current_sent = SentenceProxy()
        if not line.strip():
            # empty line: default back to sentence
            comment_for = "sentence"
            continue
        if line.startswith("# global.columns = "):
            column_names = [x.strip().lower() for x in line[19:].split("\t")]
            if len(column_names) < 2:
                column_names = [x.strip().lower() for x in line[19:].split(" ")]
            assert len(column_names) >= 2, ValueError(
                f"CONLLU files must define at least two columns: ID and FORM; got {column_names} instead."
            )
            continue
        elif line.startswith("# newdoc "):
            comment_for = "document"
            attr, val = [x.strip() for x in line[9:].split("=", 2)]
            if attr == "id":
                if current_doc.assigned:
                    current_doc.entity.make()
                current_doc = LayerProxy()
            current_doc.set_attribute(attr, val)
            continue
        elif line.startswith("# newpar "):
            comment_for = "paragraph"
            attr, val = [x.strip() for x in line[9:].split("=", 2)]
            current_par.set_attribute(attr, val)
            continue
        elif line.startswith("# sent_id "):
            comment_for = "sentence"
            assert current_doc, RuntimeError(
                "Encountered a new sentence before a new document"
            )
        if m := re.match(r"# ([^=]+)=(.+)$", line):
            attr, val = [x.strip() for x in (m[1], m[2])]
            if attr and val:
                if comment_for == "sentence":
                    current_sent.set_attribute(attr, val)
                elif comment_for == "paragraph":
                    current_par.set_attribute(attr, val)
                else:
                    current_doc.set_attribute(attr, val)
            continue
        if current_doc.assigned and current_par.attributes:
            current_par.assign_entity(
                current_doc.entity.Paragraph(
                    **{
                        x.replace("id", "parid"): y
                        for x, y in current_par.attributes.items()
                    }
                )
            )
        comment_for = "sentence"
        if not current_doc.assigned:
            current_doc.assign_entity(
                c.Document(
                    **{
                        x.replace("id", "docid"): y
                        for x, y in current_doc.attributes.items()
                    }
                )
            )
        if not current_sent.assigned:
            sent_parent = (
                current_par.entity if current_par.assigned else current_doc.entity
            )
            current_sent.assign_entity(
                sent_parent.Segment(
                    **{
                        x.replace("sent_id", "sent"): y
                        for x, y in current_sent.attributes.items()
                    }
                )
            )

        token_id, form, *rest = [
            "" if x == "_" else x.strip() for x in line.split("\t")
        ]
        if "-" in token_id:
            misc = ""
            if "misc" in column_names:
                misc = rest[column_names.index("misc") - 2]
            current_sent.mwu.append((misc, form, token_id.split("-")))
        else:
            kwargs: dict = {}
            for n, x in enumerate(column_names[2:]):
                kwargs[x] = rest[n]
                if rest[n].replace(".", "", 1).isdigit():
                    kwargs[x] = float(rest[n])
            if "feats" in column_names:
                feats_idx = column_names.index("feats")
                feats_str = rest[feats_idx - 2]
                try:
                    kwargs["feats"] = get_obj(feats_str)
                except:
                    kwargs["feats"] = feats_str
            if "misc" in column_names:
                misc_idx = column_names.index("misc")
                kwargs["misc"] = get_obj(rest[misc_idx - 2])
            token_proxy = TokenProxy()
            if "head" in kwargs:
                token_proxy.head = str(int(kwargs.pop("head")))
            if "deprel" in kwargs:
                token_proxy.deprel = kwargs.pop("deprel")
            token_proxy.assign_entity(
                current_sent.entity.Token(
                    form,
                    **kwargs,
                )
            )
            current_sent.tokens[token_id] = token_proxy
    process_sent(c, current_sent)
    current_par = LayerProxy()
    if current_doc.assigned:
        current_doc.entity.make()
    print("Corpus created")
    return c


def process_files(fns: list[str]) -> Corpus:
    existing_files = [fn for fn in fns if os.path.isfile(fn)]

    def read_lines() -> Iterator[str]:
        for fn in existing_files:
            with open(fn, "r") as input:
                tab_columns = "\t".join(CONLLU_COLUMNS)
                yield f"# global.columns = {tab_columns}"
                no_ext = Path(fn).stem
                yield f"# newdoc id = {no_ext}"
                while line := input.readline():
                    yield line.rstrip("\r\n")

    corpus_name: str = (
        Path(existing_files[0]).stem if len(existing_files) == 1 else "Untitled corpus"
    )
    c = create_corpus(read_lines(), corpus_name)
    return c
