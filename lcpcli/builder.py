# TODO: left_anchor and right_anchor in relation layers

import csv
import json
import os
import re
import tempfile
import shutil

from typing import Any
from uuid import uuid4

from .utils import esc, sorted_dict, NestedSet

ANCHORINGS = ("stream", "time", "location")
# ATYPES = ("text", "categorical", "number", "dict", "labels")
ATYPES_LOOKUP = ("text", "dict", "labels")
NAMEDATALEN = 63


def get_layer_method(layer: "Layer"):
    corpus = layer._corpus

    def layer_method(*args, **kwargs):
        if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            # global attribute
            corpus._layers.pop(layer._name, "")
            fname = f"{layer._name.lower()}.csv"
            corpus._files[fname].close()
            corpus._files.pop(fname)
            return GlobalAttribute(corpus, layer._name, args[0])
        largs = [a for a in args]
        if layer._name == corpus._token and isinstance(largs[0], str):
            form = largs.pop(0)
            layer.form = form
        if len(largs) > 0:
            assert all(isinstance(c, Layer) for c in largs), RuntimeError()
            layer.add(*largs)
        for aname, avalue in kwargs.items():
            setattr(layer, aname, avalue)
        return layer

    def make_all(*args: Layer):
        if len(args) < 1:
            return
        assert all(isinstance(a, Layer) for a in args), RuntimeError(
            "Can only make a list of layers"
        )
        mapping = corpus._layers[args[0]._name]
        relation_attrs: set[str] = set()
        # find the two relational attributes (type entity)
        for a in args:
            for aname, attr in a._attributes.items():
                if attr._type != "entity":
                    continue
                relation_attrs.add(aname)
            if len(relation_attrs) >= 2:
                break
        if not relation_attrs:
            # Not a relational layer: make and return
            for a in args:
                a.make()
            return
        # source is the attribute that's missing in at least one layer
        source_a = next(
            ra for ra in relation_attrs if any(ra not in a._attributes for a in args)
        )
        target_a = next(ra for ra in relation_attrs if ra != source_a)
        # reference nested sets by target's id
        nested_sets = {
            a._attributes[target_a]._value._id: NestedSet(
                a._attributes[target_a]._value._id
            )
            for a in args
        }
        roots = []
        for a in args:
            target_id = a._attributes[target_a]._value._id
            if source_a not in a._attributes:
                # a layer without a source is a root
                roots.append(nested_sets[target_id])
                continue
            # add this layer's target as a child of the source
            source_id = a._attributes[source_a]._value._id
            nested_sets[source_id].add(nested_sets[target_id])
        # compute all the roots
        for r in roots:
            r.compute_anchors(mapping.nested_set_counter)
            mapping.nested_set_counter = r.right + 1
        # now it's time to make the layers
        for a in args:
            target_id = a._attributes[target_a]._value._id
            nested_set = nested_sets[target_id]
            a._nested_set = [nested_set.left, nested_set.right]
            a.make()

    setattr(layer_method, "make", make_all)

    return layer_method


class LayerMapping:
    def __init__(self, layer: "Layer"):
        corpus = layer._corpus
        lname = layer._name.lower()
        self.csvs: dict[str, Any] = {"_main": corpus._csv_writer(f"{lname}.csv")}
        if layer._name == corpus._segment:
            self.csvs["_fts"] = corpus._csv_writer(f"fts_vector.csv")
            self.csvs["_fts"].writerow([f"{lname}_id", "vector"])
        self.attributes: dict[str, Any] = {}
        self.lookups: dict[str, Any] = {}
        self.counter = 0
        self.nested_set_counter: int = 1
        self.contains: list[str] = []
        self.anchorings: list[str] = []
        if layer._name in (corpus._token, corpus._segment):
            self.anchorings.append("stream")
        self.media: None | dict = None


class Corpus:
    def __init__(
        self,
        name: str,
        document: str = "Document",
        segment: str = "Segment",
        token: str = "Token",
        authors: str = "placeholder",
        institution: str = "",
        description: str = "placeholder",
        date: str = "placeholder",
        revision: int | float = 1,
        url: str = "placeholder",
        license: str | None = None,
    ):
        self._name = name
        self._document = document
        self._segment = segment
        self._token = token
        self._layers: dict[str, LayerMapping] = {}
        self._files: dict[str, Any] = {}
        self._char_counter: int = 0
        self._global_attributes: dict[str, dict] = {}
        self._authors = authors
        self._institution = institution
        self._corpus_description = description
        self._date = date
        self._revision = revision
        self._url = url
        self._license = license
        self._upperFrameDocument = 0

    def _csv_writer(self, fn: str):
        tmp = tempfile.NamedTemporaryFile(
            "w+", encoding="utf-8", newline="\n", delete=False
        )
        self._files[fn] = tmp
        return csv.writer(tmp)

    def _add_layer(self, layer_name: str):
        layer: Layer = Layer(layer_name, self)
        if layer._name not in self._layers:
            layer_mapping = LayerMapping(layer)
            self._layers[layer._name] = layer_mapping
        if layer_name == self._segment:
            layer._id = str(uuid4())
        return layer

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_"):
            super().__setattr__(name, value)
        # elif name in ("document", "segment", "token"):
        else:
            setattr(self, f"_{name}", value)

    def __getattribute__(self, name: str):
        if name in ("document", "segment", "token"):
            return getattr(self, f"_{name}")
        elif re.match(r"[A-Z]", name):
            layer = self._add_layer(name)
            return get_layer_method(layer)
        return super().__getattribute__(name)

    def make(self, destination: str = "./", is_global: dict = {}):
        # second pass + write final files
        for layer_name, mapping in self._layers.items():
            lname = layer_name.lower()
            headers = [f"{lname}_id"]
            if mapping.media:
                headers.append("name")
                headers.append("media")
            if layer_name == self._token:
                headers.append(f"{self._segment.lower()}_id")
            for a in ANCHORINGS:
                if a not in mapping.anchorings:
                    continue
                if a == "stream":
                    headers.append("char_range")
                if a == "time":
                    headers.append("frame_range")
                if a == "location":
                    headers.append("xy_box")
            is_relation = any(
                a["type"] == "entity" for a in mapping.attributes.values()
            )
            if is_relation:
                headers = []
                if mapping.nested_set_counter > 1:
                    headers.append("left_anchor")
                    headers.append("right_anchor")
            header_n_to_attr: dict[int, str] = {}
            labels: dict[int, int] = {}
            texts_to_categorical: dict[int, str] = {}
            for na, (aname, aopts) in enumerate(
                mapping.attributes.items(), start=len(headers)
            ):
                atype = aopts["type"]
                lookup = {}
                if atype in ATYPES_LOOKUP:
                    lookup = mapping.lookups[aname]
                if atype == "text":
                    is_token = layer_name == self._token
                    can_categorize = (
                        not (is_token and aname in ("form", "lemma"))
                        and len(lookup) <= 100
                        and all(len(v) < NAMEDATALEN for v in lookup)
                    )
                    if can_categorize:
                        texts_to_categorical[na] = aname
                        headers.append(aname)
                    else:
                        headers.append(f"{aname}_id")
                elif atype == "labels":
                    labels[na] = len(lookup)
                    headers.append(aname)
                elif atype in ATYPES_LOOKUP or atype == "ref":
                    headers.append(f"{aname}_id")
                else:
                    headers.append(aname)
                header_n_to_attr[na] = aname
            lfn = f"{lname}.csv"
            ifile = self._files[lfn]
            ifile.seek(0)
            with open(os.path.join(destination, lfn), "w") as output:
                csv_writer = csv.writer(output)
                csv_writer.writerow(headers)
                for row in csv.reader(ifile):
                    # fill in missing columns
                    for nr in range(len(row), len(headers)):
                        aname = header_n_to_attr[nr]
                        aopts = mapping.attributes[aname]
                        if aopts["type"] not in ("text", "dict"):
                            row.append("")
                            continue
                        lookup = mapping.lookups[aname]
                        lookupval: Any = (
                            "" if aopts["type"] == "text" else json.dumps(dict({}))
                        )
                        lookupid: int | None = lookup.get(lookupval, None)
                        if lookupid is None:
                            lookupid = len(lookup) + 1
                            lookup[lookupval] = lookupid
                            mapping.csvs[aname].writerow([lookupid, lookupval])
                        row.append(str(lookupid))
                    # optimize each column that needs to be optimized
                    for nc, val in enumerate(row):
                        if nc in labels:
                            while len(val) < labels[nc]:
                                val = f"0{val}"
                            row[nc] = val
                        if nc in texts_to_categorical:
                            aname = texts_to_categorical[nc]
                            row[nc] = next(
                                k
                                for k, v in mapping.lookups[aname].items()
                                if str(v) == val
                            )
                    csv_writer.writerow(row)
            for aname in texts_to_categorical.values():
                mapping.attributes[aname]["type"] = "categorical"
                afn = f"{lname}_{aname.lower()}.csv"
                tmp_path = self._files[afn].name
                self._files[afn].close()
                os.remove(tmp_path)
                self._files.pop(afn, "")
                print(
                    f"Turned {layer_name}->{aname} from text to categorical; delete lookup file"
                )
            tmp_path = ifile.name
            ifile.close()
            os.remove(tmp_path)
            self._files.pop(lfn, "")
        # remaining files
        for fn, f in self._files.items():
            tmp_path = f.name
            f.close()
            shutil.copy(tmp_path, os.path.join(destination, fn))
            os.remove(tmp_path)
        config: dict[str, Any] = {
            "meta": {
                "name": self._name,
                "authors": self._authors,
                "corpusDescription": self._corpus_description,
                "date": self._date,
                "url": self._url,
                "revision": 1,
            },
            "firstClass": {
                "token": self._token,
                "segment": self._segment,
                "document": self._document,
            },
            "layer": {},
        }
        if self._institution:
            config["meta"]["institution"] = self._institution
        if self._license:
            config["meta"]["license"] = self._license
        if self._global_attributes:
            config["globalAttributes"] = {
                k.lower(): {"type": "dict", "keys": v["keys"]}
                for k, v in self._global_attributes.items()
            }
        if media := self._layers[self._document].media:
            config["meta"]["mediaSlots"] = {
                k: {"mediaType": v, "isOptional": False} for k, v in media.items()
            }
        for layer, mapping in self._layers.items():
            toconf: dict = {
                "anchoring": {"stream": False, "time": False, "location": False},
                "layerType": "unit",
                "attributes": {},
            }
            is_relation = any(
                a["type"] == "entity" for a in mapping.attributes.values()
            )
            for a in mapping.anchorings:
                toconf["anchoring"][a] = True
            if is_relation:
                toconf.pop("anchoring")
                toconf["layerType"] = "relation"
            if mapping.contains:
                toconf["contains"] = sorted(
                    mapping.contains,
                    key=lambda c: c not in (self._token, self._segment, self._document),
                )[0]
                toconf["layerType"] = "span"
            for aname, aopts in mapping.attributes.items():
                aname_in_conf = aname
                ais_global = aname in is_global.get(layer, {})
                if ais_global:
                    aopts["isGlobal"] = True
                if aopts["type"] == "categorical" and not ais_global:
                    aopts["values"] = [v for v in mapping.lookups[aname]]
                elif aopts["type"] == "ref":
                    aopts.pop("type")
                    aopts.pop("nullable", "")
                elif aopts["type"] == "entity":
                    aopts.pop("type")
                    aopts["name"] = aname
                    if "source" in toconf["attributes"] or aopts.get("nullable"):
                        aname_in_conf = "target"
                    else:
                        aname_in_conf = "source"
                toconf["attributes"][aname_in_conf] = aopts
            if mapping.nested_set_counter > 1:
                toconf["attributes"]["left_anchor"] = {"type": "number"}
                toconf["attributes"]["right_anchor"] = {"type": "number"}
            config["layer"][layer] = toconf
        with open(os.path.join(destination, "config.json"), "w") as config_output:
            config_output.write(json.dumps(config, indent=4))


class Layer:
    def __init__(self, name: str, corpus: Corpus):
        self._name = name
        self._attributes: dict[str, Attribute] = {}
        self._corpus = corpus
        self._anchorings: dict[str, list] = {}
        self._contains: list[Layer] = []
        self._parents: list[Layer] = []
        self._id: str = ""
        self._made: bool = False
        self._media: dict | None = None
        self._nested_set: list = []

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            assert re.match(r"[a-z][a-zA-Z0-9]+", name), RuntimeError()
            Attribute(self, name, value)

    def __getattribute__(self, name: str):
        if re.match(r"[A-Z]", name):
            corpus = self._corpus
            layer = corpus._add_layer(name)
            self._contains.append(layer)
            layer._parents.append(self)
            return get_layer_method(layer)
        return super().__getattribute__(name)

    def _find_in_parents(self, parent_name: str):
        if not self._parents:
            return None
        parent = next((p for p in self._parents if p._name == parent_name), None)
        if parent:
            return parent
        for p in self._parents:
            parent = p._find_in_parents(parent_name)
            if parent:
                return parent
        return None

    def _in_stream(self, checked: set[str] = set()) -> bool:
        """
        Return True if this layer should be anchored to the stream
        In particular, if the previous sibling is stream-anchored
        """
        self_a = self._corpus._layers[self._name].anchorings
        if "stream" in self_a:
            return True
        now_checked: set[str] = checked.union({self._name})
        for p in self._parents:
            if any(
                l._in_stream(checked=now_checked)
                for l in p._contains
                if l._name not in now_checked
            ):
                self_a.append("stream")
                return True
        return False

    def _children(self, recursive: False) -> list["Layer"]:
        if not recursive:
            return self._contains
        ch: list[Layer] = []
        for c in self._contains:
            if c._contains:
                ch += c._children(recursive=True)
                continue
            ch.append(c)
        return ch

    def make(self):
        if self._made:
            return
        corpus = self._corpus
        is_token = self._name == corpus._token
        is_segment = self._name == corpus._segment
        is_relation = any(a._type == "entity" for a in self._attributes.values())
        mapping = corpus._layers[self._name]
        mapping.counter = mapping.counter + 1
        if not is_segment:
            self._id = str(mapping.counter)
        rows = [self._id]
        if self._media:
            doc_name = f"{self._name} {self._id}"
            if "name" in self._attributes:
                name_attr = self._attributes.pop("name")
                doc_name = name_attr._value
                assert len(doc_name) < NAMEDATALEN, RuntimeError(
                    f"Found a {self._name} named '{doc_name}': names must have less than {NAMEDATALEN} characters"
                )
            rows.append(doc_name)
            rows.append(json.dumps(self._media))
        if is_token:
            seg_parent = self._find_in_parents(corpus._segment)
            rows.append(seg_parent._id)
            char_low = corpus._char_counter
            corpus._char_counter = (
                corpus._char_counter + len(self._attributes["form"]._value) + 1
            )
            self._anchorings["stream"] = [char_low, corpus._char_counter]
        elif self._contains:
            unset_anchorings = {a for a in ANCHORINGS if not self._anchorings.get(a)}
            for child in self._contains:
                child.make()
                if child._name not in mapping.contains:
                    mapping.contains.append(child._name)
                # Anchorings
                for a in unset_anchorings:
                    if a not in child._anchorings:
                        continue
                    child_a = child._anchorings[a]
                    if a not in self._anchorings:
                        self._anchorings[a] = [*child_a]
                    self_a = self._anchorings[a]
                    if child_a[0] < self_a[0]:
                        self_a[0] = child_a[0]
                    if a == "time" and self._name == corpus._document:
                        if corpus._upperFrameDocument < self_a[0]:
                            self_a[0] = corpus._upperFrameDocument
                        corpus._upperFrameDocument = self_a[1]
                    if a != "location":
                        if child_a[1] > self_a[1]:
                            self_a[1] = child_a[1]
                        continue
                    if child_a[1] < self_a[1]:
                        self_a[1] = child_a[1]
                    if child_a[2] > self_a[2]:
                        self_a[2] = child_a[2]
                    if child_a[3] > self_a[3]:
                        self_a[3] = child_a[3]
            if is_segment:
                tokens = [
                    ch._attributes.values()
                    for ch in self._children(recursive=True)
                    if ch._name == corpus._token
                ]
                fts = [
                    " ".join(
                        f"'{na+1}{esc(attr._value)}':{nt+1}"
                        for na, attr in enumerate(attrs)
                        if attr._type in ("categorical", "text")
                    )
                    for nt, attrs in enumerate(tokens)
                ]
                if fts:
                    mapping.csvs["_fts"].writerow([self._id, " ".join(fts)])
        # occupy at least 1 char in the stream if anchored
        if not self._anchorings.get("stream") and self._in_stream():
            self._anchorings["stream"] = [
                corpus._char_counter,
                corpus._char_counter + 1,
            ]
            corpus._char_counter += 1
        for a in self._anchorings:
            if a in mapping.anchorings:
                continue
            mapping.anchorings.append(a)
        for anc_name in ANCHORINGS:
            if anc_name not in self._anchorings:
                continue
            anc_val = self._anchorings[anc_name]
            v = f"[{anc_val[0]},{anc_val[1]})"
            if anc_name == "location":
                v = f"({anc_val[0]},{anc_val[1]}),({anc_val[2]},{anc_val[3]})"
            rows.append(v)
        # Add any new attribute to mapping
        for aname, attr in self._attributes.items():
            if aname in mapping.attributes:
                continue
            atype = attr._type
            mapping.attributes[aname] = {
                "type": atype,
                "nullable": (
                    True if mapping.counter > 1 else False
                ),  # adding a new attribute
            }
            if atype == "ref":
                mapping.attributes[aname]["ref"] = attr._ref.lower()
            elif atype in ATYPES_LOOKUP:
                if aname not in mapping.lookups:
                    mapping.lookups[aname] = {}
                if aname not in mapping.csvs:
                    fn = f"{self._name.lower()}_{aname.lower()}.csv"
                    mapping.csvs[aname] = corpus._csv_writer(fn)
                    if atype == "labels":
                        mapping.csvs[aname].writerow(["bit", "label"])
                    else:
                        anamelow = aname.lower()
                        mapping.csvs[aname].writerow([f"{anamelow}_id", anamelow])
        # All attributes
        if is_relation:
            rows = []
            assert self._nested_set or mapping.nested_set_counter == 1, RuntimeError(
                "All dependency layer instances must be made the same way: either by calling make statically, or by calling it on each instance."
            )
            if self._nested_set:
                left_anchor, right_anchor = self._nested_set
                rows.append(left_anchor)
                rows.append(right_anchor)
        for aname, aopts in mapping.attributes.items():
            attr = self._attributes.get(aname, None)
            atype = aopts["type"]
            val = attr._value if attr else ""
            if val in (None, ""):
                assert not is_token or aname != "form", RuntimeError(
                    "Token cannot have an empty form!"
                )
                aopts["nullable"] = True
            if atype == "entity" and val:
                aopts["entity"] = attr._ref
                assert isinstance(val, Layer), RuntimeError(
                    f"Reference to a non-layer entity ({attr})"
                )
                assert val._made, RuntimeError(
                    f"Entity referenced in relation layer {self._name} not made yet ({val})"
                )
                val = val._id
            if atype in ATYPES_LOOKUP:
                alookup = mapping.lookups[aname]
                if atype == "labels":
                    lab_ids = []
                    for lab in val:
                        nlab = alookup.get(lab, None)
                        if nlab is None:
                            nlab = len(alookup)
                            mapping.csvs[aname].writerow([nlab, lab])
                        alookup[lab] = nlab
                        lab_ids.append(nlab)
                    nlabels = int(aopts.get("nlabels", len(alookup)))
                    aopts["nlabels"] = len(alookup)
                    bits = ["1" if n in lab_ids else "0" for n in range(nlabels)]
                    val = "".join(b for b in reversed(bits))
                else:
                    lookupid = alookup.get(val, None)
                    if lookupid is None:
                        lookupid = len(alookup) + 1
                        alookup[val] = lookupid
                        mapping.csvs[aname].writerow([lookupid, val])
                    val = lookupid
            if atype == "dict":
                keys = mapping.attributes[aname].setdefault("keys", {})
                for k, v in json.loads(attr._value).items():
                    if k in keys:
                        continue
                    keys[k] = {
                        "type": (
                            "dict"
                            if isinstance(v, dict)
                            else ("number" if isinstance(v, (int, float)) else "text")
                        )
                    }
            if val is None:
                val = ""
            elif val in (True, False):
                val = int(val)
            val = str(val)
            rows.append("" if val == None else str(val))
        mapping.csvs["_main"].writerow(rows)
        self._made = True
        return self

    def set_time(self, *args):
        if len(args) == 2:
            self._anchorings["time"] = args
        elif args[0] is False:
            self._anchorings.pop("time", "")
        return self

    def get_time(self) -> list[int]:
        return self._anchorings.get("time", [])

    def set_char(self, *args):
        assert self._name != self._corpus._token, RuntimeError(
            "Cannot manually set the char_range of tokens"
        )
        if len(args) == 2:
            self._anchorings["stream"] = args
        elif args[0] is False:
            self._anchorings.pop("stream", "")
        return self

    def get_char(self) -> list[int]:
        return self._anchorings.get("stream", [])

    def set_xy(self, *args):
        if len(args) == 4:
            self._anchorings["location"] = args
        elif args[0] is False:
            self._anchorings.pop("location", "")
        return self

    def get_xy(self) -> list[int]:
        return self._anchorings.get("location", [])

    def set_media(self, name: str, file: str, media_type: str | None = None):
        assert self._name == self._corpus._document, RuntimeError(
            "Cannot set media on non-document layer"
        )
        if self._media is None:
            self._media = {}
        self._media[name] = file
        mapping = self._corpus._layers[self._name]
        if mapping.media is None:
            mapping.media = {}
        if media_type is None:
            media_type = "audio"
            if file.lower().endswith(
                (".mp4", ".avi", ".mov", ".wmv", ".webm", ".flv", ".mkv")
            ):
                media_type = "video"
        mapping.media[name] = media_type
        return self

    def add(self, *layers: "Layer"):
        assert not self._contains or all(
            l._name == self._contains[0]._name for l in layers
        ), RuntimeError("All the children of a layer must be of the same type")
        self._contains += layers
        for layer in layers:
            if self not in layer._parents:
                layer._parents.append(self)
        return self


class Attribute:
    def __init__(self, layer: Layer, name: str, value: Any = None):
        self._name = name
        self._value = value
        self._layer = layer
        self._ref = None
        atype = "text"
        if isinstance(value, (list, set)):
            atype = "labels"
        elif isinstance(value, dict):
            atype = "dict"
            value = {
                k: ",".join(x for x in v) if isinstance(v, (list, set)) else v
                for k, v in value.items()
            }
            self._value = json.dumps(sorted_dict(value))
        elif isinstance(value, (int, float)):
            atype = "number"
        elif isinstance(value, GlobalAttribute):
            atype = "ref"
            self._ref = value._name
            self._value = value._id
        elif isinstance(value, Layer):
            atype = "entity"
            self._ref = value._name
        self._type: str = atype
        layer._attributes[name] = self


class GlobalAttribute:
    def __init__(self, corpus: Corpus, name: str, value: dict = {}):
        self._name = name
        value = {
            k: ",".join(x for x in v) if isinstance(v, (list, set)) else v
            for k, v in value.items()
        }
        self._value = value
        if name not in corpus._global_attributes:
            lname = name.lower()
            csv_writer = corpus._csv_writer(f"global_attribute_{lname}.csv")
            csv_writer.writerow([f"{lname}_id", lname])
            corpus._global_attributes[name] = {
                "csv": csv_writer,
                "ids": {},
                "keys": {
                    k: {
                        "type": (
                            "dict"
                            if isinstance(v, dict)
                            else ("number" if isinstance(v, (int, float)) else "text")
                        )
                    }
                    for k, v in value.items()
                },
            }
        mapping = corpus._global_attributes[name]
        self._id = str(value.get("id", len(mapping["ids"]) + 1))
        mapping["ids"][self._id] = 1
        mapping["csv"].writerow([self._id, json.dumps(value)])
