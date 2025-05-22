import csv
import json
import os
import re
import tempfile
import shutil

from typing import Any
from uuid import uuid4

# ATYPES = ("text", "categorical", "number", "dict", "labels")
ATYPES_LOOKUP = ("text", "dict", "labels")


def get_layer_method(layer: "Layer"):
    corpus = layer._corpus

    def layer_method(*args, **kwargs):
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

    return layer_method


class LayerMapping:
    def __init__(self, layer: "Layer"):
        corpus = layer._corpus
        lname = layer._name.lower()
        self.csv: dict[str, Any] = {"_main": corpus._csv_writer(f"{lname}.csv")}
        if layer._name == corpus._segment:
            self.csv["_fts"] = corpus._csv_writer(f"fts_vector.csv")
            self.csv["_fts"].writerow([f"{lname}_id", "vector"])
        self.attributes: dict[str, Any] = {}
        self.lookups: dict[str, Any] = {}
        self.counter = 0
        self.contains: list[str] = []
        self.anchorings: list[str] = []
        if layer._name == corpus._token:
            self.anchorings.append("stream")


class Corpus:
    def __init__(
        self,
        name: str,
        document: str = "Document",
        segment: str = "Segment",
        token: str = "Token",
    ):
        self._name = name
        self._document = document
        self._segment = segment
        self._token = token
        self._layers: dict[str, LayerMapping] = {}
        self._files: dict[str, Any] = {}
        self._char_counter: int = 0
        self._global_attributes: dict[str, dict] = {}

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

    def make(self, destination: str = "./"):
        # second pass + write final files
        for layer_name, mapping in self._layers.items():
            lname = layer_name.lower()
            headers = [f"{lname}_id"]
            if layer_name == self._token:
                headers.append(f"{self._segment.lower()}_id")
            for a in mapping.anchorings:
                if a == "stream":
                    headers.append("char_range")
                if a == "time":
                    headers.append("frame_range")
                if a == "location":
                    headers.append("xy_box")
            n_non_attr_headers = len(headers)
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
                        and len(lookup) <= 50
                        and all(len(v) < 65 for v in lookup)
                    )
                    if can_categorize:
                        texts_to_categorical[na] = aname
                        aopts["type"] = "categorical"
                        headers.append(aname)
                        afn = f"{lname}_{aname.lower()}.csv"
                        tmp_path = self._files[afn].name
                        self._files[afn].close()
                        os.remove(tmp_path)
                        self._files.pop(afn, "")
                    else:
                        headers.append(f"{aname}_id")
                elif atype == "labels":
                    labels[na] = len(lookup)
                    headers.append(aname)
                elif atype in ATYPES_LOOKUP:
                    headers.append(f"{aname}_id")
                else:
                    headers.append(aname)
            lfn = f"{lname}.csv"
            ifile = self._files[lfn]
            ifile.seek(0)
            with open(os.path.join(destination, lfn), "w") as output:
                csv_writer = csv.writer(output)
                csv_writer.writerow(headers)
                for row in csv.reader(ifile):
                    while len(row) < len(headers):
                        row.append("")
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
                "author": "placeholder",
                "corpusDescription": "placeholder",
                "date": "placeholder",
                "version": 1,
            },
            "firstClass": {
                "token": self._token,
                "segment": self._segment,
                "document": self._document,
            },
            "layer": {},
        }
        for layer, mapping in self._layers.items():
            toconf: dict = {
                "anchoring": {"stream": False, "time": False, "location": False},
                "layerType": "unit",
                "attributes": {},
            }
            for a in mapping.anchorings:
                toconf["anchoring"][a] = True
            if mapping.contains:
                toconf["contains"] = mapping.contains[0]
                toconf["layerType"] = "span"
            for aname, aopts in mapping.attributes.items():
                if aopts["type"] == "categorical":
                    aopts["values"] = [v for v in mapping.lookups[aname]]
                toconf["attributes"][aname] = aopts
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

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            assert re.match(r"[a-z][a-zA-Z0-9]+", name), RuntimeError()
            Attribute(self, name, value)

    def find_in_parents(self, parent_name: str):
        if not self._parents:
            return None
        parent = next((p for p in self._parents if p._name == parent_name), None)
        if parent:
            return parent
        for p in self._parents:
            parent = p.find_in_parents(parent_name)
            if parent:
                return parent
        return None

    def make(self):
        if self._made:
            return
        corpus = self._corpus
        is_token = self._name == corpus._token
        is_segment = self._name == corpus._segment
        mapping = corpus._layers[self._name]
        mapping.counter = mapping.counter + 1
        if not is_segment:
            self._id = str(mapping.counter)
        rows = [self._id]
        if is_token:
            seg_parent = self.find_in_parents(corpus._segment)
            rows.append(seg_parent._id)
            char_low = corpus._char_counter
            corpus._char_counter = (
                corpus._char_counter + len(self._attributes["form"]._value) + 1
            )
            self._anchorings["stream"] = [char_low, corpus._char_counter]
        elif self._contains:
            unset_anchorings = {
                a: []
                for a in ("stream", "time", "location")
                if not self._anchorings.get(a)
            }
            fts: list[str] = []
            for nc, child in enumerate(self._contains):
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
                        continue
                    self_a = self._anchorings[a]
                    if child_a[0] < self_a[0]:
                        self_a[0] = child_a[0]
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
                if not is_segment:
                    continue
                # FTS
                fts.append(
                    " ".join(
                        f"'{na+1}{attr._value}':{nc+1}"
                        for na, attr in enumerate(child._attributes.values())
                        if attr._type in ("categorical", "text")
                    )
                )
            if fts:
                mapping.csv["_fts"].writerow([self._id, " ".join(fts)])
            for a in self._anchorings:
                if a in mapping.anchorings:
                    continue
                mapping.anchorings.append(a)
        elif is_segment:
            # segment with no tokens
            self._anchorings["stream"] = [
                corpus._char_counter,
                corpus._char_counter + 1,
            ]
            corpus._char_counter = corpus._char_counter + 1
        for anc_name, anc_val in self._anchorings.items():
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
            if atype in ATYPES_LOOKUP:
                if aname not in mapping.lookups:
                    mapping.lookups[aname] = {}
                if aname not in mapping.csv:
                    fn = f"{self._name.lower()}_{aname.lower()}.csv"
                    mapping.csv[aname] = corpus._csv_writer(fn)
                    if atype == "labels":
                        mapping.csv[aname].writerow(["bit", "label"])
                    else:
                        anamelow = aname.lower()
                        mapping.csv[aname].writerow([f"{anamelow}_id", anamelow])

        # All attributes
        for aname, aopts in mapping.attributes.items():
            attr = self._attributes.get(aname, None)
            val = attr._value if attr else ""
            if val in (None, ""):
                assert not is_token or aname != "form", RuntimeError(
                    "Token cannot have an empty form!"
                )
                aopts["nullable"] = True
            if aopts["type"] in ATYPES_LOOKUP:
                alookup = mapping.lookups[aname]
                if aopts["type"] == "labels":
                    nlabels = int(aopts.get("nlabels", len(alookup)))
                    bits = ["0" for _ in range(nlabels)]
                    for lab in val:
                        nlab = alookup.get(lab, None)
                        if nlab is None:
                            nlab = len(alookup) + 1
                            mapping.csv[aname].writerow([nlab, lab])
                        alookup[lab] = nlab
                        while len(bits) < nlab:
                            bits.append("0")
                        bits[nlab - 1] = "1"
                    aopts["nlabels"] = len(alookup)
                    val = "".join(b for b in reversed(bits))
                else:
                    lookupid = alookup.get(val, None)
                    if lookupid is None:
                        lookupid = len(alookup) + 1
                        alookup[val] = lookupid
                        mapping.csv[aname].writerow([lookupid, val])
                    val = str(lookupid)
            if val is None:
                val = ""
            elif val in (True, False):
                val = int(val)
            val = str(val)
            rows.append("" if val == None else str(val))
        mapping.csv["_main"].writerow(rows)

        self._made = 1

    def set_time(self, *args):
        if len(args) == 2:
            self._anchorings["time"] = args
        elif args[0] is False:
            self._anchorings.pop("time", "")

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

    def get_char(self) -> list[int]:
        return self._anchorings.get("char", [])

    def set_xy(self, *args):
        if len(args) == 4:
            self._anchorings["location"] = args
        elif args[0] is False:
            self._anchorings.pop("location", "")

    def get_xy(self) -> list[int]:
        return self._anchorings.get("location", [])

    def add(self, *layers: "Layer"):
        assert not self._contains or all(
            l._name == self._contains[0]._name for l in layers
        ), RuntimeError("All the children of a layer must be of the same type")
        self._contains += layers
        for layer in layers:
            if self not in layer._parents:
                layer._parents.append(self)


class Attribute:
    def __init__(self, layer: Layer, name: str, value: Any = None):
        self._name = name
        self._value = value
        self._layer = layer
        atype = "text"
        if isinstance(value, (list, set)):
            atype = "labels"
        elif isinstance(value, dict):
            atype = "dict"
        elif isinstance(value, (int, float)):
            atype = "number"
        self._type = atype
        layer._attributes[name] = self


class GlobalAttribute:
    def __init__(self, corpus: Corpus, name: str, value: dict = {}):
        self._name = name
        self._value = value
        if name not in corpus._global_attributes:
            lname = name.lower()
            corpus._global_attributes[name] = {
                "csv": corpus._csv_writer(f"global_attribute_{lname}.csv"),
                "ids": {},
            }
        mapping = corpus._global_attributes[name]
        self._id = str(value.get("id", len(mapping["ids"]) + 1))
        mapping["ids"][self._id] = 1
        mapping["csv"].writerow([self._id, value])
