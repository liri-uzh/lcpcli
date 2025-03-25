"""
Parser and writer for CONLLU-style data


ID: Word index, integer starting at 1 for each new sentence; may be a range for multiword tokens; may be a decimal number for empty nodes (decimal numbers can be lower than 1 but must be greater than 0).
FORM: Word form or punctuation symbol.
LEMMA: Lemma or stem of word form.
UPOS: Universal part-of-speech tag.
XPOS: Language-specific part-of-speech tag; underscore if not available.
FEATS: List of morphological features from the universal feature inventory or from a defined language-specific extension; underscore if not available.
HEAD: Head of the current word, which is either a value of ID or zero (0).
DEPREL: Universal dependency relation to the HEAD (root iff HEAD = 0) or a defined language-specific subtype of one.
DEPS: Enhanced dependency graph in the form of a list of head-deprel pairs.
MISC: Any other annotation.

"""

import re
import uuid

from typing import cast

from ._parser import Parser
from ..utils import (
    Attribute,
    Categorical,
    CustomDict,
    Dependency,
    Document,
    Meta,
    Segment,
    Text,
    Token,
    parse_csv,
)

RESERVED_KEYS = {"document": ["media"]}


FEATURES = [
    "id",
    "form",
    "lemma",
    "upos",
    "xpos",
    "feats",
    "head",
    "deprel",
    "deps",
    "misc",
]


class CONLLUParser(Parser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.word = CustomDict()
        self.lemma = CustomDict()
        self.ufeats = CustomDict()
        self.jsonbMisc = CustomDict()
        self.xpos = set()
        self.cur_idx = 1
        self.cur_word = 1
        self.cur_seg = uuid.uuid4()
        self.left = 1

        self.start_idx = re.compile(r"^\[\d+")
        self.end_idx = re.compile(r"\d+\)$")
        self.text_id = -1

        self.n_doc = 0

        self._features = FEATURES

    @property
    def right(self):
        return self.left + 1

    def parse_sentence(
        self, sentence_lines, config={}
    ) -> tuple[Segment | None, Document | None]:
        """
        Take a list of ConLLU lines (comments + tokens) and output (sentence, new_doc | None)
        """
        new_doc = None
        config = self.config or {}
        token_from_config = config.get("layer", {}).get(
            config.get("firstClass", {}).get("token"), {}
        )
        token_conf_attributes = token_from_config.get("attributes", {})
        current_sentence: dict = {"meta": {}, "text": []}
        mediaSlots = self.config.get("meta", {}).get("mediaSlots", {})
        for line in sentence_lines:
            if re.match(r"# newdoc", line):
                if not new_doc:
                    self.n_doc += 1
                    new_doc = {"meta": {}, "sentences": {}, "id": self.n_doc}
                if match := re.match(r"# newdoc id = (.+)", line):
                    new_doc["id"] = match[1]
                elif match := re.match(r"# newdoc ([^=]+) = (.+)", line):
                    key = match[1].strip()
                    assert key not in RESERVED_KEYS["document"], ValueError(
                        "The attribute name 'media' is reserved; you cannot use it yourself"
                    )
                    value = match[2].strip()
                    if mediaSlots and key in mediaSlots:
                        new_doc["media"] = new_doc.get("media", {})
                        new_doc["media"][key] = value
                    else:
                        new_doc["meta"][key] = value
            elif match := re.match(r"# sent_id = (.+)", line):
                current_sentence["id"] = match[1]
                current_sentence["meta"]["sent_id"] = match[1]
            elif match := re.match(r"#\s+([^=]+)\s+= (.+)", line):
                current_sentence["meta"][match[1]] = match[2].strip()
            elif re.match(r"\d+[\t\s]", line):
                line = line.split("\t")
                line = {k: v.strip() for k, v in zip(self._features, line)}
                current_sentence["text"].append(line)

        if new_doc:
            for media_name, attribs in mediaSlots.items():
                assert (
                    media_name in new_doc.get("media", {})
                    or attribs.get("isOptional", False) is not False
                ), KeyError(
                    f"Filename missing for required media '{media_name}' in current document"
                )

        sentence = None
        if current_sentence["text"]:
            sentence = Segment()
            for t in current_sentence["text"]:
                token = Token()
                sentence.tokens.append(token)
                for k, v in t.items():
                    if v == "_":
                        v = None
                    if k == "id":
                        token.id = v
                    elif k in ("form", "lemma"):
                        token.attributes[k] = Text(k, v)
                    elif k in ("upos", "xpos"):
                        token.attributes[k] = Categorical(k, v)
                    elif k == "feats":
                        v = v or ""
                        d = {}
                        for pkpv in v.split("|"):
                            if "=" not in pkpv:
                                continue
                            pk, pv = pkpv.split("=")
                            d[pk.strip()] = pv.strip()
                        token.attributes["ufeat"] = Meta("ufeat", d)
                    elif k == "head":
                        if v == "0":
                            v = None
                        token.attributes["deprel"] = Dependency("deprel", v)
                    elif k == "deprel":
                        dep: Dependency = cast(
                            Dependency,
                            token.attributes.get("deprel", Dependency("deprel", None)),
                        )
                        dep.label = v
                        token.attributes["head"] = dep
                    elif (
                        k == "misc"
                        or token_conf_attributes.get(k, {}).get("type") == "dict"
                    ):
                        # if not v or "=" not in v:
                        #     continue
                        kv_obj = {}
                        for pkpv in (v or "").split("|"):
                            if "=" not in pkpv:
                                continue
                            pk, *pv = pkpv.split("=")
                            pv = "=".join(pv)
                            pk = pk.strip()
                            if k != "misc":
                                kv_obj[pk] = str(pv).strip()
                                continue
                            if pk == "SpaceAfter":
                                continue
                            pv = pv.strip()
                            if pk in ("start", "end"):
                                token.frame_range = token.frame_range or [0, 0]
                                token.frame_range[0 if pk == "start" else 1] = int(
                                    25.0 * float(pv)
                                )
                            else:
                                kv_obj[pk] = str(pv)
                        attname = k.lower()
                        if k == "misc":
                            attname = (
                                "meta"
                                if "misc" not in token_conf_attributes
                                else "misc"
                            )
                        token.attributes[attname] = Meta(attname, kv_obj)
                    elif token_conf_attributes.get(k, {}).get("type") == "categorical":
                        token.attributes[k] = Categorical(k, v.rstrip())
                    else:
                        token.attributes[k] = Text(k, v)

            # if has_frame_range:
            #     assert all(t.frame_range is not None for t in sentence.tokens), AttributeError("Some tokens miss start-end time information")

            if "id" not in current_sentence:
                print("Warning: found a sentence with no sent_id")

            # sentence.tokens = current_sentence["text"]
            meta = current_sentence["meta"]
            if config:
                # If a config was provided, pop any entry from meta that's listed as a main attribute
                seg_layer = config.get("firstClass", {}).get("segment", "")
                seg_config = (
                    config.get("layer", {}).get(seg_layer, {}).get("attributes", {})
                )
                segment_containers = [
                    layer.lower()
                    for layer, props in config.get("layer", {}).items()
                    if props.get("layerType", "") == "span"
                    and props.get("contains", "") == seg_layer
                ]
                for attr_name, attr_props in seg_config.items():
                    if attr_name == "meta":
                        continue
                    name = attr_name
                    if name + "_id" in meta:
                        name = name + "_id"
                    elif name not in meta:
                        warning_msg = f"Warning: no value found for attribute '{name}' for segment {current_sentence.get('id','__ANONYMOUS__')}"
                        print(warning_msg)
                        meta[name] = ""
                        # continue
                    a = meta.pop(name)
                    attr = Attribute(name, a)
                    if attr_props.get("type") == "categorical":
                        attr = Categorical(name, a)
                    sentence.attributes[name] = attr
                for seg_container in segment_containers:
                    attr_name = next(
                        (k for k in meta.keys() if k.lower() == seg_container), None
                    )
                    if attr_name is None:
                        continue
                    sentence.attributes[attr_name] = Text(
                        attr_name, meta.pop(attr_name)
                    )
            if meta:
                # if name.lower() in segment_containers:
                #     sentence.attributes[name] = Text(name, meta.pop(name))
                sentence.attributes["meta"] = Meta("meta", meta)

        ret_doc: Document | None = None
        if new_doc:
            ret_doc = Document()
            if id := new_doc.get("id"):
                print(f"Parsing document '{id}'")
                new_doc["meta"]["name"] = id
            ret_doc.attributes["meta"] = Meta("meta", new_doc["meta"])
            if new_doc.get("media"):
                ret_doc.attributes["media"] = Meta("media", new_doc["media"])
            doc_layer = config.get("firstClass", {}).get("document", "")
            doc_config = (
                config.get("layer", {}).get(doc_layer, {}).get("attributes", {})
            )
            for attr_name in doc_config:
                name = attr_name
                if name + "_id" in new_doc["meta"]:
                    name = name + "_id"
                elif name not in new_doc["meta"]:
                    continue
                a = new_doc["meta"].pop(name)
                ret_doc.attributes[name] = Attribute(name, a)
            # doc.first_sentence = sentence

        return (sentence, ret_doc)
        # return (current_sentence, new_doc)

    def parse_generator(self, reader, config={}):
        checked_first_line_for_conllu_plus = False
        sentence_lines = []
        while line := reader.readline():
            l = line.strip()
            if l:
                if not checked_first_line_for_conllu_plus and l.startswith(
                    "# global.columns = "
                ):
                    self._features = [f.lower() for f in l[19:].split()]
                else:
                    sentence_lines.append(line)
            else:
                # empty line: new sentence
                if sentence_lines:
                    yield self.parse_sentence(sentence_lines, config=config)
                sentence_lines = []
            checked_first_line_for_conllu_plus = True

        if sentence_lines:
            yield self.parse_sentence(sentence_lines, config=config)

    def parse(self, content):
        """
        When iterator is True, yield ({id,meta,text},None|{id,meta}) -- content should have a readline method and
        When iterator is False, return a writable string
        """

        conllu_parsed = {}
        current_document = {"meta": {}, "sentences": {}}
        current_sentences = {}

        self.n_doc = 0
        n_sent = 0

        sentences = [sent for sent in content.split("\n\n") if sent]

        for sent in sentences:

            sent_list = [line for line in sent.split("\n") if line]
            sentence, new_doc = self.parse_sentence(sent_list)

            if new_doc:
                if current_sentences:
                    current_document["sentences"] = current_sentences
                    self.n_doc += 1
                    conllu_parsed[current_document.pop("id", self.n_doc)] = (
                        current_document
                    )
                current_document = new_doc
                current_sentences = {}

            current_sentences[sentence.pop("id", n_sent := n_sent + 1)] = sentence

        if current_sentences:
            current_document["sentences"] = current_sentences
            self.n_doc += 1
            conllu_parsed[current_document.pop("id", self.n_doc)] = current_document

        return conllu_parsed

    def doc_meta(self, id, meta):
        """
        content is a dict {id,meta}
        """
        lines = []
        lines.append(f"# newdoc id = {id}")
        for key, value in meta.items():
            text = value.lstrip(" ").rstrip(" ") if value else None
            if not key or not text:
                continue
            lines.append(f"# newdoc {key} = {text}")
        return f"\n".join(lines)

    def combine(self, content):
        """
        content is a dict of filepaths and conllu data strings. combine them into one corpus and return as string?

        probably we have to add the filepaths to each sentence's sent-metadata
        """

        conllu_lines = []

        for doc_id, doc_content in content.items():
            conllu_lines.append(self.doc_meta(doc_id, doc_content.get("meta", {})))
            conllu_lines.append(self.write(doc_content.get("sentences", {})))

        return f"\n".join(conllu_lines)

    def write_sentence(self, sentence):
        lines = []
        sent_meta, sent_text = {}, []

        for item in sentence:
            if "meta" in item:
                sent_meta = sentence[item]
            elif "text" in item:
                sent_text = sentence[item]

        for k, v in sent_meta.items():
            lines.append("# {} = {}\n".format(k, v))

        if not sent_text:
            return lines

        lines.append(
            f"# text = {' '.join([token.get('form',' ') for token in sent_text])}\n"
        )

        for n, item in enumerate(sent_text):
            lines.append("\t".join([item.get(f, "_") for f in self._features]))

        return lines

    def write_generator(self, generator):
        self.n_doc = 0
        n_sent = 0

        for sentence, doc in generator:
            lines = []
            # For now we don't support combine=False: yield new docs
            if doc:
                self.n_doc += 1
                lines.append("# newdoc id = {}".format(doc.pop("id", self.n_doc)))
                for k, v in doc.get("meta", {}).items():
                    lines.append("# newdoc {} = {}".format(k, v))
            lines.append(
                "# sent_id = {}\n".format(sentence.pop("id", n_sent := n_sent + 1))
            )
            lines += self.write_sentence(sentence)
            yield "".join(lines)

    def write(self, content, filename=None, combine=True, meta={}):
        """
        content is a dict of sentences: key is the id, value is {meta,text}
        """

        conllu_lines = []

        for sent_id, sent_data in content.items():

            if conllu_lines:
                conllu_lines.append(f"")  # Add an empty line

            conllu_lines.append(f"# sent_id = {sent_id}\n")
            conllu_lines += self.write_sentence(sent_data)

        return f"\n".join(conllu_lines)
