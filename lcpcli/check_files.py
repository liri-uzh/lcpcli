import csv
import json
import os

from jsonschema import validate
from re import match
from uuid import UUID

EXTENSIONS = (".csv", ".tsv")
LOOKUP_TYPES = ("dict", "text")

# TODO: categorical
# TODO: labels
# TODO: deprel


def is_lookup(p: dict) -> bool:
    return p.get("type", "") in LOOKUP_TYPES or "ref" in p


class Checker:

    def __init__(self, config, **kwargs):
        self.config = config
        self.token = config.get("firstClass", {}).get("token", "")
        self.segment = config.get("firstClass", {}).get("segment", "")
        self.document = config.get("firstClass", {}).get("document", "")
        self.quote = kwargs.get("quote") or '"'
        self.delimiter = kwargs.get("delimiter") or ","
        self.escape = kwargs.get("escape") or None

    def parseline(self, line) -> list[str]:
        return next(
            csv.reader(
                [line],
                delimiter=self.delimiter,
                quotechar=self.quote,
                escapechar=self.escape,
            )
        )

    def is_anchored(self, layer: str, anchor: str) -> bool:
        layer_conf = self.config["layer"][layer]
        if layer_conf.get("anchoring", {}).get(anchor, False) == True:
            return True
        contained_layer = layer_conf.get("contains", "")
        if contained_layer in self.config["layer"]:
            return self.is_anchored(contained_layer, anchor)
        return False

    def check_uuid(self, uuid: str) -> None:
        assert UUID(uuid, version=4), SyntaxError(f"Invalid UUID ({uuid})")

    def check_dict(self, str_obj: str) -> None:
        try:
            json_obj = json.loads(str_obj)
        except:
            json_obj = None
        assert isinstance(json_obj, dict), SyntaxError(
            f"Invalid syntax for dict entry ({str_obj})"
        )
        return None

    def check_ftsvector(self, vector: str) -> None:
        units = vector.split(" ")
        for unit in units:
            assert unit.startswith("'"), SyntaxError(
                f"Each value in the tsvector must start with a single quote character ({unit})"
            )
            assert match(r"'\d+", unit), SyntaxError(
                f"Each value in the tsvector must start with a single quote character followed by an integer index ({unit})"
            )
            m = match(r"'\d+(.*)':\d+$", unit)
            assert m, SyntaxError(
                f"Each value in the tsvector must end with a single quote followed by a colon and an integer index ({unit})"
            )
            assert not m[1] or match(r"^([^']|'')+$", m[1]), SyntaxError(
                f"Each value in the tsvector must double the mid-text single-quote characters"
            )
        return None

    def check_range(self, range: str, name: str) -> None:
        m = match(r"\[(\d+),(\d+)\)", range)
        assert m, SyntaxError(f"Range '{name}' not in the right format: {range}")
        l, u = (m[1], m[2])
        try:
            li = int(l)
        except:
            raise ValueError(f"Invalid lower bound in range '{name}': {l}")
        try:
            ui = int(u)
        except:
            raise ValueError(f"Invalid upper bound in range '{name}': {u}")
        assert li >= 0, ValueError(
            f"Lower bound of range '{name}' cannot be negative: {l}"
        )
        assert ui >= 0, ValueError(
            f"Upper bound of range '{name}' cannot be negative: {u}"
        )
        assert ui > li, ValueError(
            f"Upper bound of range '{name}' ({ui}) must be strictly greater than its lower bound ({li})"
        )
        return None

    def check_xy_box(self, xy_box: str, name: str) -> None:
        m = match(r"\((\d+),(\d+)\),\((\d+),(\d+)\)", xy_box)
        assert m, SyntaxError(f"Range '{name}' not in the right format: {xy_box}")
        x1, y1, x2, y2 = (m[1], m[2], m[3], m[4])
        try:
            x1i = int(x1)
        except:
            raise SyntaxError(f"Invalid x1 in xy_box '{name}': {x1}")
        try:
            y1i = int(y1)
        except:
            raise SyntaxError(f"Invalid x1 in xy_box '{name}': {y1}")
        try:
            x2i = int(x2)
        except:
            raise SyntaxError(f"Invalid x1 in xy_box '{name}': {x2}")
        try:
            y2i = int(y2)
        except:
            raise SyntaxError(f"Invalid x1 in xy_box '{name}': {y2}")
        assert x2i > x1i, ValueError(
            f"x2 in xy_box '{name}' ({x2i}) must be strictly greater than x1 ({x1i})"
        )
        assert y2i > y1i, ValueError(
            f"y2 in xy_box '{name}' ({y2i}) must be strictly greater than y1 ({y1i})"
        )
        return None

    def check_attribute_name(self, name: str) -> None:
        assert name == name.lower(), SyntaxError(
            f"Attribute name '{name}' cannot contain uppercase characters"
        )
        assert " " not in name, SyntaxError(
            f"Attribute name '{name}' cannot contain whitespace characters"
        )
        assert "'" not in name, SyntaxError(
            f"Attribute name '{name}' cannot contain single-quote characters"
        )
        return None

    def check_attribute_file(
        self,
        path: str,
        layer_name: str,
        attribute_name: str,
        attribute_props: dict,
    ) -> None:
        attribute_low = attribute_name.lower()
        lay_att = f"{layer_name.lower()}_{attribute_low}"
        typ = attribute_props.get("type", "")
        fpath = os.path.join(path, f"{lay_att}.csv")
        if not os.path.exists(fpath):
            fpath = fpath.replace(".csv", ".tsv")
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named {lay_att}.csv for attribute '{attribute_name}' of type {typ} for layer '{layer_name}'"
        )
        filename = os.path.basename(fpath)
        with open(fpath, "r") as afile:
            header = self.parseline(afile.readline())
            assert f"{attribute_low}_id" in header, ReferenceError(
                f"Column {attribute_low}_id missing from file {filename} for attribute '{attribute_name}' of type {typ} for layer {layer_name}"
            )
            assert attribute_low in header, ReferenceError(
                f"Column {attribute_low} missing from file {filename} for attribute '{attribute_name}' of type {typ} for layer {layer_name}"
            )
        return None

    def check_global_attribute_file(self, path: str, glob_attr: str) -> None:
        glob_attr_low = glob_attr.lower()
        fpath = os.path.join(path, f"global_attribute_{glob_attr_low}.csv")
        if not os.path.exists(fpath):
            fpath = fpath.replace(".csv", ".tsv")
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named global_attribute_{glob_attr_low}.csv for global attribute '{glob_attr}'"
        )
        filename = os.path.basename(fpath)
        with open(fpath, "r") as afile:
            header = self.parseline(afile.readline())
            assert f"{glob_attr_low}_id" in header, ReferenceError(
                f"Column {glob_attr_low}_id missing from file {filename} for global attribute '{glob_attr}'"
            )
            assert f"{glob_attr_low}" in header, ReferenceError(
                f"Column {glob_attr_low} missing from file {filename} for global attribute '{glob_attr}'"
            )
        return None

    def check_labels_file(self, path: str, layer_name: str, aname: str) -> None:
        layer_low = layer_name.lower()
        fpath = os.path.join(path, f"{layer_low}_labels.csv")
        if not os.path.exists(fpath):
            fpath = fpath.replace(".csv", ".tsv")
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named {layer_low}_labels.csv for attribute '{aname}' of type labels on layer {layer_name}"
        )
        filename = os.path.basename(fpath)
        with open(fpath, "r") as afile:
            header = self.parseline(afile.readline())
            assert "bit" in header, ReferenceError(
                f"Column bit missing from file {filename} for labels attribute '{aname}' on layer {layer_name}"
            )
            assert "label" in header, ReferenceError(
                f"Column label missing from file {filename} for labels attribute '{aname}' on layer {layer_name}"
            )
        return None

    def check_layer(
        self, path: str, layer_name: str, layer_props: dict, add_zero: bool = False
    ) -> None:
        token_layer = self.token
        segment_layer = self.segment

        layer_low = layer_name.lower()
        anchored_stream = self.is_anchored(layer_name, "stream")
        anchored_time = self.is_anchored(layer_name, "time")
        anchored_location = self.is_anchored(layer_name, "location")

        fpath = os.path.join(
            path,
            layer_low
            + (
                "0.csv"
                if add_zero and layer_name in (token_layer, segment_layer)
                else ".csv"
            ),
        )
        if not os.path.exists(fpath):
            fpath = fpath.replace(".csv", ".tsv")
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named {layer_low}.csv for layer '{layer_name}'"
        )
        filename = os.path.basename(fpath)
        with open(fpath, "r") as layer_file:
            header = self.parseline(layer_file.readline())
            if layer_props.get("layerType") == "relation":
                # TODO: check relational attributes
                return
            assert f"{layer_low}_id" in header, ReferenceError(
                f"Could not find a column named {layer_low}_id in {filename}"
            )
            assert not anchored_stream or "char_range" in header, ReferenceError(
                f"Column 'char_range' missing from file {filename} for stream-anchored layer {layer_name}"
            )
            assert not anchored_time or "frame_range" in header, ReferenceError(
                f"Column 'frame_range' missing from file {filename} for time-anchored layer {layer_name}"
            )
            assert not anchored_location or "xy_box" in header, ReferenceError(
                f"Column 'frame_range' missing from file {filename} for time-anchored layer {layer_name}"
            )
            if layer_name == token_layer:
                assert f"{segment_layer.lower()}_id" in header, ReferenceError(
                    f"Column '{segment_layer.lower()}_id' missing from file {filename} for token-level layer {layer_name}"
                )
            for aname, aprops in layer_props.get("attributes", {}).items():
                self.check_attribute_name(aname)
                acol = f"{aname}_id" if is_lookup(aprops) else aname
                typ = aprops.get("type", "")
                ref = aprops.get("ref")
                lookup = typ in LOOKUP_TYPES
                assert acol in header, ReferenceError(
                    f"Column '{acol}' is missing from file {filename} for the attribute '{aname}' of layer {layer_name}"
                )
                if lookup:
                    self.check_attribute_file(path, layer_name, aname, aprops)
                if typ == "labels":
                    self.check_labels_file(path, layer_name, aname)
                if ref:
                    self.check_global_attribute_file(path, ref)
        return None

    def check_config(self) -> None:
        mandatory_keys = ("layer", "firstClass", "meta")
        for key in mandatory_keys:
            assert key in self.config, ReferenceError(
                f"The configuration file must contain the main key '{key}'"
            )
        layer = self.config.get("layer", {})
        if first_class := self.config.get("firstClass", {}):
            assert isinstance(first_class, dict), TypeError(
                f"The value of 'firstClass' must be a key-value object with the keys 'document', 'segment' and 'token'"
            )
            mandatory_keys = ("document", "segment", "token")
            for key in mandatory_keys:
                assert key in first_class, ReferenceError(
                    f"firstClass must contain the key '{key}'"
                )
                assert not layer or first_class[key] in layer, ReferenceError(
                    f"layer must contain the key '{first_class[key]}' defined for {key}"
                )
        parent_dir = os.path.dirname(__file__)
        schema_path = os.path.join(parent_dir, "data", "lcp_corpus_template.json")
        with open(schema_path) as schema_file:
            validate(self.config, json.loads(schema_file.read()))
            print("validated json schema")
        return None

    def run_checks(
        self, directory: str, full: bool = True, add_zero: bool = False
    ) -> None:
        self.check_config()
        layer = self.config.get("layer", {})
        for layer_name, layer_properties in layer.items():
            self.check_layer(directory, layer_name, layer_properties, add_zero)
        if not full:
            return None
        for filename in os.listdir(directory):
            if not filename.endswith(EXTENSIONS):
                continue
            no_ext, *_ = os.path.splitext(filename)
            columns = {}
            if no_ext.startswith("global_attribute_"):
                aname = no_ext[17:].lower()
                props = self.config.get("globalAttributes", {}).get(aname)
                assert props, ReferenceError(
                    f"No correpsonding global attribute defined in the configuration for file {filename}"
                )
                columns = {f"{aname}_id": "lookup", aname: "dict"}
            elif no_ext == "fts_vector":
                columns = {
                    f"{self.segment.lower()}_id": "uuid",
                    "vector": "ftsvector",
                }
            elif "_" in no_ext:
                lname, aname, *remainder = no_ext.split("_")
                assert not remainder, SyntaxError(f"Invalid filename: {filename}")
                props = next(
                    (v for k, v in layer.items() if k.lower() == lname.lower()), None
                )
                assert props, ReferenceError(
                    f"No corresponding layer found for file {filename}"
                )
                aprops = next(
                    (
                        v
                        for k, v in props.get("attributes", {}).items()
                        if k.lower() == aname.lower()
                    ),
                    None,
                )
                assert aprops, ReferenceError(
                    f"Found a file named {filename} but the configuration defines no such attribute for that layer"
                )
                or_type = " or ".join(LOOKUP_TYPES)
                typ = aprops.get("type", "")
                assert typ in LOOKUP_TYPES, ValueError(
                    f"Found a file named {filename} even though the corresponding attribute is not of type {or_type}"
                )
                columns = {f"{aname}_id": "lookup", aname: typ}
            else:
                layer_name = next(
                    (l for l in layer.keys() if l.lower() == no_ext.lower()), ""
                )
                if not layer_name and add_zero and no_ext.endswith("0"):
                    layer_name = next(
                        (l for l in layer.keys() if l.lower() == no_ext[:-1].lower()),
                        "",
                    )
                assert layer_name, ReferenceError(
                    f"No corresponding layer found for file {filename}"
                )
                props = layer[layer_name]
                if props.get("layerType", "") == "relation":
                    # TODO: implement this
                    continue
                columns = {
                    (f"{k}_id" if is_lookup(v) else k): (
                        "lookup" if is_lookup(v) else v.get("type", "")
                    )
                    for k, v in props.get("attributes", {}).items()
                }
                columns[f"{layer_name.lower()}_id"] = (
                    "uuid" if layer_name == self.segment else "int"
                )
                if layer_name == self.token:
                    columns[f"{self.segment.lower()}_id"] = "uuid"
                if self.is_anchored(layer_name, "stream"):
                    columns["char_range"] = "range"
                if self.is_anchored(layer_name, "time"):
                    columns["frame_range"] = "range"
                if self.is_anchored(layer_name, "location"):
                    columns["xy_box"] = "xy_box"
                media_slots = self.config["meta"].get("mediaSlots", {})
                if media_slots and layer_name == self.document:
                    columns["name"] = "text"
                    columns["media"] = "dict"

            with open(os.path.join(directory, filename), "r") as input:
                headers: list[str] = []
                counter = 0
                while line := input.readline():
                    counter += 1
                    cols = self.parseline(line)
                    if not headers:
                        headers = cols
                        for h in headers:
                            assert h in columns, ReferenceError(
                                f"Found unexpected column named {h} in {filename}"
                            )
                        continue
                    assert len(cols) == len(headers), SyntaxError(
                        f"Found {len(cols)} values on line {counter} in {filename}, expected {len(cols)}."
                    )
                    for n, col in enumerate(cols):
                        typ = columns[headers[n]]
                        if typ == "int":
                            try:
                                int(col)
                            except:
                                raise ValueError(
                                    f"Excepted int value for column {n} ({headers[n]}) on line {counter} in {filename}, got {col} ({line})"
                                )
                        else:
                            try:
                                if typ == "dict":
                                    self.check_dict(col)
                                # elif typ == "labels":
                                #     self.check_labels(col)
                                elif typ == "range":
                                    self.check_range(col, headers[n])
                                elif typ == "xy_box":
                                    self.check_xy_box(col, headers[n])
                                elif typ == "uuid":
                                    self.check_uuid(col)
                                elif typ == "ftsvector":
                                    self.check_ftsvector(col)
                            except Exception as e:
                                raise ValueError(
                                    f"{e} ({headers[n]} in {filename}:{counter}:{n} -- {line})"
                                )
        return None
