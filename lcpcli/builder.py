import csv
import re
import tempfile

from typing import Any
from uuid import uuid4

ATYPES = ("text", "categorical", "number", "dict", "labels")
ATYPES_LOOKUP = ("text", "dict", "labels")


def get_layer_method(layer: "Layer"):
    corpus = layer._corpus

    def layer_method(*args, **kwargs):
        if layer._name == corpus._token and isinstance(args[0], str):
            form = args.pop(0)
            layer.form = form
        if len(args) > 1:
            assert all(isinstance(c, Layer) for c in args), RuntimeError()
            children_name = args[0]._name
            assert all(c._name == children_name for c in args), RuntimeError()
            layer._contains = children_name
        for aname, avalue in kwargs.items():
            setattr(layer, aname, avalue)
        layer._process()

    return layer_method


class LayerMapping:
    def __init__(self, layer: "Layer"):
        corpus = layer._corpus
        lname = layer._name.lower()
        self.files: dict[str, Any] = {"_main": corpus._csv_writer(f"{lname}.csv")}
        self.attributes: dict[str, Any] = {}
        self.lookups: dict[str, Any] = {}
        self.id = 0


class Corpus:
    def __init__(
        self,
        name: str,
        document: str = "Document",
        segment: str = "Segment",
        token: str = "Token",
    ):
        self._name = (name,)
        self._document = document
        self._segment = segment
        self._token = token
        self._layers: dict[str, LayerMapping] = {}
        self._files: dict[str, Any] = {}
        self._char_counter: int = 0

    def _csv_writer(self, fn: str):
        tmp = tempfile.NamedTemporaryFile(
            "w", encoding="unicode", newline="\n", delete=False
        )
        self._files[fn] = tmp
        return csv.writer(tmp)

    def _add_layer(self, layer_name: str):
        layer: Layer = Layer(layer_name, self)
        if layer._name not in self._layers:
            layer_mapping = LayerMapping(layer)
            self._layers[layer._name] = layer_mapping
        layer_mapping = self._layers[layer._name]
        layer_mapping.id = layer_mapping.id + 1
        if layer_name == self._segment:
            layer._id = str(uuid4())
        else:
            layer._id = str(layer_mapping.id)

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_"):
            super().__setattr__(name, value)
        # elif name in ("document", "segment", "token"):
        else:
            setattr(self, f"_{name}", value)

    def __getattribute__(self, name: str):
        if name.startswith("_"):
            return super().__getattribute__(name)
        if name in ("document", "segment", "token"):
            return getattr(self, f"_{name}")
        if re.match(r"[A-Z]", name):
            layer = self._add_layer(name)
            return get_layer_method(layer)

    def _process(self):
        # process lookups
        pass


class Layer:
    def __init__(self, name: str, corpus: Corpus):
        self._name = name
        self._attributes: dict[str, Any] = {}
        self._corpus = corpus
        self._anchorings: dict[str, Any] = {}
        self._contains: str = ""
        self._parent: Layer | None = None
        self._id: str = ""

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            assert re.match(r"[a-z][a-zA-Z0-9]+", name), RuntimeError()
            Attribute(self, name, value)

    def _process(self):
        corpus = self._corpus
        is_token = self._name == corpus._token
        mapping = corpus._layers[self._name]
        rows = [self._id]
        if is_token:
            rows.append(self._parent._id)
        # for a in self._anchorings.values():
        #     rows.append(a)
        # Process any new attribute
        for aname, aopts in self._attributes.items():
            if aname in mapping.attributes:
                continue
            atype = aopts["type"]
            mapping.attributes[aname] = {
                "type": atype,
                "nullable": True if self._id > 1 else False,  # adding a new attribute
            }
            if atype in ATYPES_LOOKUP:
                if aname not in mapping.lookups:
                    mapping.lookups[aname] = {}
                if aname not in mapping.files:
                    fn = f"{self._name.lower()}_{aname.lower()}.csv"
                    mapping.files[aname] = corpus._csv_writer(fn)
        # All attributes
        for aname, aopts in mapping.attributes.items():
            val = self._attributes.get(aname, None)
            if val in (None, ""):
                assert not is_token or aname != "form", RuntimeError(
                    "Token cannot have an empty form!"
                )
                aopts["nullable"] = True
            if aopts["type"] in ATYPES_LOOKUP:
                alookup = mapping.lookups[aname]
                lookupid = alookup.get(val, None)
                if lookupid is None:
                    lookupid = len(alookup) + 1
                    alookup[val] = lookupid
                    mapping.files[aname].writerow([str(lookupid), str(val)])
                val = str(lookupid)
            rows.append("" if val == None else str(val))
        mapping.files["_main"].writerow(rows)


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
        self._lookup = False
        layer._attributes[name] = self
