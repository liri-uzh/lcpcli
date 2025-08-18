import csv
import io
import json
import os
import re
import uuid

from datetime import date
from pathlib import Path


def is_anchored(entity: dict, config: dict, anchor: str) -> bool:
    if "anchoring" in entity:
        return entity["anchoring"].get(anchor, False)
    if entity.get("contains", "") in config.get("layer", {}):
        return is_anchored(config["layer"][entity["contains"]], config, anchor)
    return False


def is_char_anchored(entity: dict, config: dict) -> bool:
    return is_anchored(entity, config, "stream")


def is_time_anchored(entity: dict, config: dict) -> bool:
    return is_anchored(entity, config, "time")


def to_csv(values: list[str], delimiter=",", quotechar='"', escapechar=None) -> str:
    with io.StringIO() as strio:
        csv.writer(
            strio, delimiter=delimiter, quotechar=quotechar, escapechar=escapechar
        ).writerow(values)
        return strio.getvalue()


def parse_csv(line, delimiter=",", quotechar='"', escapechar=None) -> list[str]:
    return next(
        csv.reader(
            [line],
            delimiter=delimiter,
            quotechar=quotechar,
            escapechar=escapechar,
        )
    )


def get_ci(d: dict, p: str, default={}):
    """
    Case-insensitive get on an object
    """
    return next((v for n, v in d.items() if n.lower() == p.lower()), default)


def get_file_from_base(fn: str, files: list[str]) -> str:
    out_fn = next((f for f in files if Path(f).stem.lower() == fn.lower()), None)
    assert out_fn, FileNotFoundError(f"Could not find a file for {fn}")
    return out_fn


def esc(
    value: str | int,
    quote: str = '"',
    double: bool = True,
    escape_backslash: bool = False,
) -> str:
    return (
        str(value)
        .replace("'", "''" if double else "'")
        .replace("\\n", "")
        .replace("\\", "\\\\" if escape_backslash else "\\")
        .replace(quote, quote + quote)
    )


def sorted_dict(d: dict) -> dict:
    ret = {}
    for k in sorted(d):
        v = d[k]
        if isinstance(v, dict):
            v = sorted_dict(v)
        elif isinstance(v, list):
            v = sorted(v)
        ret[k] = v
    return ret


class CustomDict:
    def __init__(self, is_ufeat=False):
        self._dictionary = {}
        self._max = 1

    def __str__(self):
        return str(dict(sorted(self._dictionary)))

    def update(self, value):
        if value and value not in self._dictionary:
            self._dictionary[value] = self._max
            self._max += 1

    def get(self, value):
        return self._dictionary.get(value, None)


class NestedSetTreeStructure:
    """
    Represents a tree structure with the nested set approach.
    """

    def __init__(self, key, left, right):
        self.nodes = {}
        if not right - left == 1:
            raise Exception("invalid anchors for initialization")
        self.nodes[key] = [left, right]

    def __str__(self):
        """
        Returns a pretty-print version of the tree.
        """
        lines = []
        last_left = 0
        indent = -1
        for key, node in sorted(self.nodes.items(), key=lambda item: item[1]):
            if node[0] - last_left == 1:
                indent += 1
            elif node[0] - last_left > 2:
                indent -= 1
            lines.append(
                "{}{}  [{},{}]".format(
                    (indent - 1) * "│  " + ("" if node[0] == 1 else "├─╴"),
                    key,
                    node[0],
                    node[1],
                )
            )
            last_left = node[0]
        return "\n".join(lines)

    def shift_anchors(self, parent_left):
        """
        Makes space in the tree by incrementing all nodes to the right by 2.
        """
        for key, node in self.nodes.items():
            if node[0] > parent_left:
                self.nodes[key][0] += 2
            if node[1] > parent_left:
                self.nodes[key][1] += 2

    def add_node(self, key, parent):
        """
        Adds a node giving the id of the parent or None for the root node.
        """
        if parent is None:
            if len(self.nodes):
                raise Exception("there can only be one root node")
            else:
                self.nodes[key] = [1, 2]
        else:
            if parent in self.nodes:
                parent_node = self.nodes[parent]
            else:
                raise Exception("key does not exist: {}".format(parent))
            self.shift_anchors(parent_node[0])
            self.nodes[key] = [parent_node[0] + 1, parent_node[0] + 2]


class Sentence:
    _space_after = re.compile(r"(?<=SpaceAfter=)(Yes|No)")
    _frame_range = re.compile(r"(?<=start=)(\d+(.\d+)?\|end=\d+(.\d+)?)")

    @staticmethod
    def valid_lines(lines):
        ret_lines = []

        for line in lines:
            if line.startswith("#"):
                continue
            toks = [x if x != "_" else None for x in line.split("\t")]
            # valid CoNNL-U?
            assert len(toks) == 10
            # make sure ID and form present
            assert [x for x in toks[:2]]
            # skip contracted tokens and ellpsis
            if "-" in toks[0] or "." in toks[0]:
                continue

            ret_lines.append(toks)

        return ret_lines

    @staticmethod
    def jsonify_ufeats(string):
        if string:
            # change angular brackets to parens
            string = string.replace("[", "(").replace("]", ")")
            # put alternatves inside JSON-array
            string = re.sub(r"(\w+,\s*\w+)", r"[\1]", string)
            # convert pipes -separator to comma
            string = string.replace("|", ",")
            # converts equal to colon
            string = string.replace("=", ":")
            # surround literals with double quotes
            string = re.sub(r"([\w()]+)", r'"\1"', string)

            return "{" + string + "}"
        else:
            return None

    @staticmethod
    def _append(lst, elem):
        """custom append function

        in contrast to the built-in method, this function returns
        the augmented list - useful for recursive calls
        """
        lst.append(elem)

        return lst

    @staticmethod
    def _traverse(hierarchy, graph, ids):
        """traverse flat list & build hierarchical structure

        the flat structure is a parent: children dict
        """
        for id in ids:
            hierarchy[id] = Sentence._traverse({}, graph, graph[id])

        return hierarchy

    @staticmethod
    def _ord_keys(dic, key_list):
        """traverse tree structure & build flat list"""
        for el, vals in dic.items():
            Sentence._ord_keys(vals, Sentence._append(key_list, el))

        return key_list

    @staticmethod
    def _esc(string, **kwargs):
        return esc(string, **kwargs)

    def __init__(self, lines, parser):
        self._comments = [l for l in lines if l.startswith("# ")]
        self._lines = self.valid_lines(lines)
        self.parser = parser
        self.proc_lines = []
        self.segment = []
        self.deprel = []
        self.fts_vector = []
        self.docs = []
        self.meta = {}

    def _tree_ins_order(self):
        """put list in hierarchical order for inserting

        1. create dictionary structure (recursively)
        2. flatten keys recursively into list
        3. go over original list and append to
           return list according to flattened keys
        """
        # index 2 = id, index 4 = head ATTENTION: adjust, if this changes!
        id_par = [(x[0], x[6]) for x in self._lines]
        ret_list = []

        # get root and check iff one
        root = [id for (id, parent) in id_par if parent == "0"]
        if len(root) != 1:
            raise Exception("root error")

        # flat parent:children mapping initialization
        graph = {id: set() for (id, parent) in id_par}

        # flat parent:children mapping building
        for id, parent in id_par:
            if parent != "0":
                graph[parent].add(id)

        # sorting in reverse, since inserting is done by shifting to the right
        graph_sort = {
            k: sorted(v, key=lambda x: int(x), reverse=True) for k, v in graph.items()
        }

        # build hierarchical structure
        hier_ids = self._traverse({}, graph, root)

        # flatten keys into ordered list
        flat_keys = self._ord_keys(hier_ids, [])

        # re-order original rows for returning
        for i in flat_keys:
            for pair in id_par:
                if pair[0] == i:
                    ret_list.append(pair)
                    continue

        return ret_list

    def _process_tree(self, ins, token_dict, tok_par_dict):
        sent = []
        fts_str = ""
        root, rest = ins[0], ins[1:]
        tree = NestedSetTreeStructure(root[0], self.parser.left, self.parser.right)
        for elem in rest:
            tree.add_node(*elem)

        # update globals
        self.parser.left = max([x[1] for x in tree.nodes.values()]) + 1

        # look-up running indices and flatten into list
        for k, v in tree.nodes.items():
            token_id = token_dict[k][0]
            deprel = token_dict[k][1]
            head_id = token_dict[tok_par_dict[k]][0] if tok_par_dict[k] else None
            sent.append((head_id, token_id, deprel, *v))

        self.deprel += sent

        # 4 = label_out (what am I?), 5 = labels_in (what do I encompass?)
        # enumerate tokens that are not multi-word units
        tok_id2sent_idx = {
            v[0]: n
            for n, (k, v) in enumerate(token_dict.items(), start=1)
            if "-" not in k
        }
        for elem in sent:
            val = self._esc(elem[2])
            fts_str += f" '4{val}':{tok_id2sent_idx[elem[1]]}"
            fts_str += f" '5{val}':{tok_id2sent_idx[elem[1]]}"

        return fts_str

    def _process_lines(self):
        # set up local variables
        token_dict = {}
        tok_par_dict = {}
        fts_str = ""
        start_char = self.parser.cur_idx
        end_char = None

        n_fts = 1
        for line in self._lines:
            w_id, word, lemma, upos, xpos, ufeats, p_id, deprel, _, misc = line

            try:
                assert w_id
                assert word
            except:
                continue

            l_word = len(word)
            end_char = self.parser.cur_idx + l_word
            ufeats = self.jsonify_ufeats(ufeats)

            # update global dicts
            self.parser.word.update(word)
            self.parser.lemma.update(lemma)
            self.parser.ufeats.update(ufeats)
            xpos and self.parser.xpos.update(xpos)

            # dictionary holding all info for 1 token
            # TODO: this is not right 100% since w_id not always unique...
            # word_id, form_fk, lemma_fk, upos, xpos, ufeat_fk, char_range, seg_fk
            token_dict[w_id] = [
                self.parser.cur_word,  # 0
                self.parser.word.get(word),  # 1
                self.parser.lemma.get(lemma),  # 2
                upos,  # 3
                xpos,  # 4
                self.parser.ufeats.get(ufeats),  # 5
                (self.parser.cur_idx, end_char),  # 6
                self.parser.cur_seg,  # 7
                deprel,  # 8
            ]

            fts_str += f" '1{self._esc(word, escape_backslash=True)}':{n_fts}"
            if lemma:
                fts_str += f" '2{self._esc(lemma, escape_backslash=True)}':{n_fts}"
            if upos:
                # escaping UPOS not needed
                fts_str += f" '3{upos}':{n_fts}"
            if xpos:
                fts_str += f" '6{self._esc(xpos, escape_backslash=True)}':{n_fts}"
            n_fts += 1

            # update global word id and index
            self.parser.cur_idx += l_word + 1

            if misc:
                if parse_misc := re.search(Sentence._space_after, misc):
                    if parse_misc[1] == "No":
                        self.parser.cur_idx -= 1
                if frame_range := re.search(Sentence._frame_range, misc):
                    start, end = frame_range[1].split("|")
                    start = round(25.0 * float(start))
                    end = round(25.0 * float(end.lstrip("end=")))
                    if end <= start:
                        end = start + 1
                    token_dict[w_id].append([start, end])
                jsonbMisc = {}
                for bit in misc.split("|"):
                    if "=" not in bit:
                        continue
                    key, value = bit.split("=")
                    if key in ("SpaceAfter", "start", "end"):
                        continue
                    jsonbMisc[key] = value
                if jsonbMisc:
                    jsonbMisc = {x: jsonbMisc[x] for x in sorted(jsonbMisc)}
                    jd = json.dumps(jsonbMisc)
                    self.parser.jsonbMisc.update(jd)
                    token_dict[w_id].append(self.parser.jsonbMisc.get(jd))

            self.parser.cur_word += 1

            tok_par_dict[w_id] = p_id if p_id != "0" else None

        # create line entry for writing
        self.proc_lines = [
            line[:6]
            + [f"[{line[6][0]},{line[6][1]})"]
            + [line[7]]
            + [(f"[{x[0]},{x[1]})" if isinstance(x, list) else x) for x in line[9:]]
            for line in token_dict.values()
        ]

        # build tree (if possible)
        # smth like "id IS_PARSED:"
        if True:
            try:
                ins = self._tree_ins_order()
                fts = self._process_tree(
                    ins, {k: (v[0], v[-1]) for k, v in token_dict.items()}, tok_par_dict
                )
            except:
                fts = ""

        # create segment entry for writing
        self.segment = [self.parser.cur_seg, f"[{start_char},{end_char})"]

        self.fts_vector = [self.parser.cur_seg, f"{fts_str}{fts}"]

        # set new segment id
        self.parser.cur_seg = uuid.uuid4()

        for l in self._comments:
            if " = " not in l:
                continue
            k, v = l.split(" = ")
            if k.startswith("# newdoc"):
                continue
            k = k[2:].strip()
            v = v.strip()
            if not k or not v:
                continue
            self.meta[k] = v

        # TODO
        # create doc entry for writing
        # For simple CoNLL-U, we assume hole corpus one doc...
        # if self._id:
        #     if self._id in self.glob.docs:
        #         self.glob.docs[self._id][1] = end_char
        #     else:
        #         self.glob.docs[self._id] = [start_char, end_char]

    def process(self):
        self._process_lines()


class Info:
    def __init__(self, **params):
        self.params = params


class Table:
    def __init__(self, name, path, config={}):
        self.name = name
        self.path = os.path.join(path, f"{name}.csv")
        assert not os.path.exists(self.path), FileExistsError(
            f"Output file '{self.path}' already exists."
        )
        self.file = open(self.path, "w", encoding="utf-8")
        self.config = config
        self.cursor = 1
        self.current_entity = dict()
        self.previous_entity = None
        self.col_names = []
        self.labels = dict()
        self.texts = dict()
        self.deps = dict()
        self.anchor_right = 0
        self.sep = ","
        self.quote = '"'
        self.trigger_character = "'"
        self.categorical_values: dict[str, set] = {}
        self.aligned_cols: dict[str, list[str]] = dict()  # {fk: [cols]}

    def write(self, row: list):
        self.file.write(
            self.sep.join(
                [
                    (
                        f"{self.quote}{esc(x, self.quote, double=False)}{self.quote}"
                        if self.trigger_character in str(x)
                        or self.sep in str(x)
                        or self.quote in str(x)
                        else str(x)
                    )
                    for x in row
                ]
            )
            + "\n"
        )


class TokenTable(Table):
    def __init__(self, name, path, config={}):
        super().__init__(name, path, config)
        self.real_attributes = {}


class LookupTable(Table):
    def __init__(self, parent_name, own_name, path, config={}):
        super().__init__(parent_name + "_" + own_name, path, config)
        self.write([own_name + "_id", own_name])

    def get_id(self, value):
        id = self.texts.get(value, 0)
        if id < 1:
            id = self.cursor
            self.cursor += 1
            self.texts[value] = id
            self.write([str(id), value])
        return str(id)


class Attribute:
    def __init__(self, name, value):
        self.name = name
        self._value = value

    @property
    def value(self):
        if not self._value:
            return ""
        else:
            return str(self._value)


class Meta(Attribute):
    def __init__(self, name, value):
        super().__init__(name, value)

    @property
    def value(self):
        if not self._value:
            return "{}"
        else:
            return json.dumps(self._value)


class Text(Attribute):
    def __init__(self, name, value):
        super().__init__(name, value)


class Categorical(Attribute):
    def __init__(self, name, value):
        super().__init__(name, value)


class Dependency(Attribute):
    def __init__(self, name, value):
        super().__init__(name, value)
        self.label = ""


# class Jsonb(Attribute):
#     def __init__(self,name,value):
# super().__init__(name,value)


class EntityType:
    def __init__(self):
        self.id: int | str = ""
        self.attributes: dict[str, Attribute] = {}


token_id = 0


class Token(EntityType):
    def __init__(self):
        super().__init__()
        global token_id
        token_id += 1
        self.id = token_id
        self.attributes["form"] = Text("form", "")
        self.spaceAfter = True
        self.frame_range = None


class Segment(EntityType):
    def __init__(self):
        super().__init__()
        self.id = uuid.uuid4()
        self.tokens: list[Token] = []


doc_id = 0


class Document(EntityType):
    def __init__(self):
        super().__init__()
        global doc_id
        doc_id += 1
        self.id = doc_id
        self.char_range_start: int = 0
        self.frame_range: list[int] = [0, 0]
        self.left = 1
        self.right = 2


# Compute left/right from parent only once
class NestedSet:
    def __init__(self, id, label="", cursor=0):
        self.id = id
        self.children = []
        self.parent = None
        self.label = label
        self.cursor_id = cursor
        self.consumed = False

    def compute_anchors(self, left=1):
        self.left = left
        for c in self.children:
            left = c.compute_anchors(left=left + 1)
        self.right = left + 1
        return self.right

    @property
    def all_ids(self):
        ids = [self.id]
        for c in self.children:
            ids += c.all_ids
        return ids

    def add(self, child):
        if child in self.children:
            return
        self.children.append(child)
        child.parent = self


def default_json(name):
    return {
        "meta": {
            "name": name,
            "authors": "Anonymous",
            "date": date.today().strftime("%Y-%m-%d"),
            "revision": 1,
            "corpusDescription": "",
        },
        "firstClass": {"document": "Document", "segment": "Segment", "token": "Token"},
        "layer": {
            "Token": {
                "abstract": False,
                "layerType": "unit",
                "anchoring": {"location": False, "stream": True, "time": False},
            },
            "Segment": {"abstract": False, "layerType": "span", "contains": "Token"},
            "Document": {
                "abstract": False,
                "contains": "Segment",
                "layerType": "span",
            },
        },
    }
