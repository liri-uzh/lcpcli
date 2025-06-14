import csv
import json
import os
import sys

from jsonschema import validate
from re import match, findall
from typing import Callable
from uuid import UUID

EXTENSIONS = (".csv", ".tsv")
LOOKUP_TYPES = ("dict", "text")
NAMEDATALEN = 63


def is_lookup(p: dict) -> bool:
    return p.get("type", "") in LOOKUP_TYPES or "ref" in p


def try_filename(path: str, no_ext: str) -> str:
    fpath = os.path.join(path, f"{no_ext}.tsv")
    if not os.path.exists(fpath):
        fpath = fpath.replace(".tsv", ".csv")
    return fpath


class Checker:

    def __init__(self, config, **kwargs):
        # hack to circumvent errors on windows (ref: https://stackoverflow.com/a/15063941)
        maxInt = sys.maxsize
        while True:
            try:
                csv.field_size_limit(maxInt)
                break
            except OverflowError:
                maxInt = int(maxInt / 10)
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

    def get_attribute_columns(
        self, attrs: dict[str, dict]
    ) -> dict[str, tuple[str, str]]:
        ret = {}
        for aname, aprops in attrs.items():
            self.check_attribute_name(aname)
            lookup = is_lookup(aprops)
            acol = f"{aname}_id" if lookup else aname
            typ = "lookup" if lookup else aprops.get("type", "")
            ret[aname] = (acol, typ)
        return ret

    def is_anchored(self, layer: str, anchor: str) -> bool:
        layer_conf = self.config["layer"][layer]
        if "anchoring" in layer_conf:
            return layer_conf["anchoring"].get(anchor, False)
        contained_layer = layer_conf.get("contains", "")
        if contained_layer in self.config["layer"]:
            return self.is_anchored(contained_layer, anchor)
        return False

    def check_uuid(self, uuid: str) -> None:
        assert UUID(uuid, version=4), SyntaxError(f"Invalid UUID ({uuid})")

    def check_categorical(self, value: str, values: None | list[str]) -> None:
        assert len(value.encode("utf-8")) <= NAMEDATALEN, ValueError(
            f"Found a categorical value ('{value}') that exceeds the database's limit of {NAMEDATALEN} bytes on enum values"
        )
        assert values is None or value in values, ValueError(
            f"Categorical value '{value}' is not in the listed values"
        )

    def check_dict(self, str_obj: str) -> None:
        try:
            json_obj = json.loads(str_obj)
        except:
            json_obj = None
        assert isinstance(json_obj, dict), SyntaxError(
            f"Invalid syntax for dict entry ({str_obj})"
        )
        return None

    def check_labels(self, bits: str, nbit: int) -> None:
        assert match(r"^[01]*$", bits), ValueError(
            f"Labels column should be series of 0s and 1s, got '{bits}'"
        )
        assert len(bits) == nbit, ValueError(
            f"Expected {nbit} bits, got {len(bits)} ('{bits}')"
        )
        return None

    def check_ftsvector(self, vector: str) -> None:
        whole_pattern = r"^('\d+([^']|'')*':\d+(\s|$))+$"
        simple_unit_pattern = r"('([^']|'')*':[^\s]+)(\s|$)"
        units = findall(simple_unit_pattern, vector)
        for n, (unit, *_) in enumerate(units):
            assert unit.startswith("'"), SyntaxError(
                f"Each value in the tsvector must start with a single quote character ({unit} -- {n})"
            )
            assert match(r"'\d+", unit), SyntaxError(
                f"Each value in the tsvector must start with a single quote character followed by an integer index ({unit} -- {n})"
            )
            m = match(r"'\d+(.*)':\d+\s?$", unit)
            assert m, SyntaxError(
                f"Each value in the tsvector must end with a single quote followed by a colon and an integer index ({unit} -- {n})"
            )
        assert match(whole_pattern, vector), SyntaxError(
            f"Invalid tsvector string ({vector})"
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
        assert len(name.encode("utf-8")) <= NAMEDATALEN, ValueError(
            f"Attribute name '{name}' exceeds the maximum length allowed in the database ({NAMEDATALEN} bytes)"
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
        fpath = try_filename(path, lay_att)
        filename = os.path.basename(fpath)
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named {filename} for attribute '{attribute_name}' of type {typ} for layer '{layer_name}'"
        )
        with open(fpath, "r", encoding="utf-8") as afile:
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
        fpath = try_filename(path, f"global_attribute_{glob_attr_low}")
        filename = os.path.basename(fpath)
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named {filename} for global attribute '{glob_attr}'"
        )
        with open(fpath, "r", encoding="utf-8") as afile:
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
        fpath = try_filename(path, f"{layer_low}_{aname.lower()}")
        filename = os.path.basename(fpath)
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named {filename} for attribute '{aname}' of type labels on layer {layer_name}"
        )
        with open(fpath, "r", encoding="utf-8") as afile:
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
        attrs = layer_props.get("attributes", {})
        columns = self.get_attribute_columns(attrs)

        no_ext: str = layer_low + (
            "0" if add_zero and layer_name in (token_layer, segment_layer) else ""
        )
        fpath = try_filename(path, no_ext)
        filename = os.path.basename(fpath)
        assert os.path.exists(fpath), FileNotFoundError(
            f"Could not find a file named {filename} for layer '{layer_name}'"
        )
        with open(fpath, "r", encoding="utf-8") as layer_file:
            header = self.parseline(layer_file.readline())
            is_relation = layer_props.get("layerType") == "relation"
            if is_relation:
                assert "source" in attrs, ReferenceError(
                    f"Could not find an attribute named 'source' for relational layer {layer_name}"
                )
                assert "target" in attrs, ReferenceError(
                    f"Could not find an attribute named 'target' for relational layer {layer_name}"
                )
                source = attrs["source"]
                target = attrs["target"]
                assert "name" in source, ReferenceError(
                    f"Could not find a name for the source attribute of relational layer {layer_name}"
                )
                assert "name" in target, ReferenceError(
                    f"Could not find a name for the source attribute of relational layer {layer_name}"
                )
                source_name = source["name"]
                target_name = target["name"]
                assert source_name in header, ReferenceError(
                    f"Could not find a column named '{source_name}' in {filename} for source attribute of relational layer {layer_name}"
                )
                assert target_name in header, ReferenceError(
                    f"Could not find a column named '{target_name}' in {filename} for target attribute of relational layer {layer_name}"
                )
            else:
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
            for aname, (acol, typ) in columns.items():
                if is_relation and aname in ("source", "target"):
                    continue
                assert acol in header, ReferenceError(
                    f"Column '{acol}' is missing from file {filename} for the attribute '{aname}' of layer {layer_name}"
                )
                if "ref" in attrs[aname]:
                    self.check_global_attribute_file(path, attrs[aname]["ref"])
                elif typ == "lookup":
                    self.check_attribute_file(path, layer_name, aname, attrs[aname])
                elif typ == "labels":
                    assert "nlabels" in attrs[aname], ReferenceError(
                        f"No 'nlabels' reported in the configuration for the attribute '{aname}' of type labels of layer {layer_name}"
                    )
                    self.check_labels_file(path, layer_name, aname)
        return None

    def check_existing_file(
        self,
        filename: str,
        directory: str,
        add_zero: bool = False,
        callback: Callable | None = None,
    ) -> None:
        layer = self.config.get("layer", {})
        layer_name = ""
        nullables = set()
        no_ext, *_ = os.path.splitext(filename)
        columns = {}
        if no_ext.startswith("global_attribute_"):
            aname = no_ext[17:].lower()
            props = self.config.get("globalAttributes", {}).get(aname)
            assert props, ReferenceError(
                f"No correpsonding global attribute defined in the configuration for file {filename}"
            )
            columns = {f"{aname}_id": "lookup", aname: "dict"}
            nullables.add(aname)
        elif no_ext == "fts_vector" or (add_zero and no_ext == "fts_vector0"):
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
            typ = aprops.get("type", "")
            if typ == "labels":
                columns = {"bit": "int", "label": "text"}
                nullables.add("label")
            else:
                or_type = " or ".join(LOOKUP_TYPES)
                assert typ in LOOKUP_TYPES, ValueError(
                    f"Found a file named {filename} even though the corresponding attribute is not of type {or_type}"
                )
                columns = {f"{aname}_id": "lookup", aname: typ}
                if aprops.get("nullable"):
                    nullables.add(aname)
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
            attrs = props.get("attributes", {})
            columns = {}
            for aname, (col_name, typ) in self.get_attribute_columns(attrs).items():
                columns[col_name] = typ
                if attrs[aname].get("nullable"):
                    nullables.add(col_name)
            if props.get("layerType", "") == "relation":
                for an in ("source", "target"):
                    columns.pop(an, "")
                    columns[attrs[an]["name"]] = (
                        "uuid" if attrs[an]["entity"] == self.segment else "int"
                    )
                    if attrs[an].get("nullable"):
                        nullables.add(attrs[an]["name"])
            else:
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

        with open(os.path.join(directory, filename), "r", encoding="utf-8") as input:
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
                    f"Found {len(cols)} values on line {counter} in {filename}, expected {len(headers)}."
                )
                if callback:
                    callback(cols, headers, filename, layer_name, self.config)
                for n, col in enumerate(cols):
                    typ = columns[headers[n]]
                    if not col:
                        assert headers[n] in nullables, ValueError(
                            f"Found an empty value for column #{n+1} ({headers[n]}) on line {counter} in {filename} even though the configuration does not reported it as nullable"
                        )
                        continue
                    if typ == "int":
                        try:
                            int(col)
                        except:
                            raise ValueError(
                                f"Excepted int value for column #{n+1} ({headers[n]}) on line {counter} in {filename}, got {col} ({line})"
                            )
                    else:
                        try:
                            if typ == "dict":
                                self.check_dict(col)
                            elif typ == "labels":
                                assert layer_name, NotImplementedError(
                                    f"Attributes of type 'labels' are only supported on layers ({filename})"
                                )
                                aprops = (
                                    layer[layer_name]
                                    .get("attributes", {})
                                    .get(headers[n], {})
                                )
                                nbit = aprops["nlabels"]
                                self.check_labels(col, nbit)
                            elif typ == "range":
                                self.check_range(col, headers[n])
                            elif typ == "xy_box":
                                self.check_xy_box(col, headers[n])
                            elif typ == "uuid":
                                self.check_uuid(col)
                            elif typ == "ftsvector":
                                self.check_ftsvector(col)
                            elif typ == "categorical":
                                assert layer_name, NotImplementedError(
                                    f"Attributes of type 'categofical' are only supported on layers ({filename})"
                                )
                                aprops = (
                                    layer[layer_name]
                                    .get("attributes", {})
                                    .get(headers[n], {})
                                )
                                values = None
                                if not aprops.get("isGlobal"):
                                    values = aprops.get("values") or None
                                self.check_categorical(col, values)
                        except Exception as e:
                            l = line.rstrip("\n")
                            raise ValueError(
                                f"{e} ({headers[n]} in {filename}:{counter}:{n+1} -- '{l}')"
                            )

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
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            validate(self.config, json.loads(schema_file.read()))
            print("validated json schema")
        return None

    def run_checks(
        self,
        directory: str,
        full: bool = True,
        add_zero: bool = False,
        callback: Callable | None = None,
    ) -> None:
        """
        Check the headers of the files corresponding to the layers in directory
        If full, also check each row
        If add_zero, will use the suffix 0 when checking token and segment files
        Callback will be run on each row (presupposes full)
        """
        self.check_config()
        layer = self.config.get("layer", {})
        for layer_name, layer_properties in layer.items():
            print(f"Checking layer {layer_name}")
            self.check_layer(directory, layer_name, layer_properties, add_zero)
        if not full:
            return None
        for filename in os.listdir(directory):
            if not filename.endswith(EXTENSIONS):
                continue
            print(f"Checking file {filename}")
            self.check_existing_file(filename, directory, add_zero, callback)
        return None
