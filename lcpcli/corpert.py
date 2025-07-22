import json
import os
import shutil
import traceback

from pandas import read_csv, isna
from time import time

from .parsers.conllu import CONLLUParser

from .cli import _parse_cmd_line
from .utils import (
    default_json,
    get_file_from_base,
    is_char_anchored,
    is_time_anchored,
    parse_csv,
    to_csv,
    LookupTable,
    Sentence,
)

from jsonschema import validate
from pathlib import Path

# map between extensions and parsers
PARSERS = {"conllu": CONLLUParser}

ERROR_MSG = """
Unrecognized input format.
Note: The converter currently supports the following formats:
.conllu, .conll
"""


class Corpert:
    @staticmethod
    def get_parsers():
        return PARSERS

    @staticmethod
    def mask(llist, n: int = 8):
        """
        computes a boolean mask to not write
        columns that are always empty.

        this is a simple heuristic which assumes that
        attrobutes that are always empty are not specified
        in the corpus template and therefore must not
        be written to the files to upload

        input is expected to be a list of
        of Sentence.proc_lines instances
        with a fixednumber of columns
        (not more or less dims)
        """
        mask = []
        for i in range(n):
            mask.append(any([x[i] for y in llist for x in y]))

        return mask

    def __init__(
        self,
        content,
        output=None,
        extension=None,
        filter=None,
        lua_filter=None,
        combine=True,
        **kwargs,
    ):
        """
        path (str): path or string of content
        combine (bool): create single output file?
        """
        self.output = os.path.abspath(output) if output else None
        self._output_format = None
        if extension:
            self._output_format = extension
        elif self.output and self.output.endswith((".conllu", ".conll")):
            self._output_format = os.path.splitext(self.output)[-1]
        if self.output and not os.path.exists(self.output) and not combine:
            os.makedirs(self.output)
        self._filter = filter
        self._lua_filter = lua_filter
        self._lua = None
        self._input_files = []
        self._path = os.path.normpath(content)
        self._combine = combine
        self._on_disk = True
        if os.path.isfile(content):
            self._input_files.append(content)
        elif os.path.isdir(content):
            # for root, dirs, files in os.walk(content):
            for file in os.listdir(content):
                # for file in files:
                # fullpath = os.path.join(root, file)
                fullpath = os.path.join(content, file)
                self._input_files.append(fullpath)
        elif isinstance(content, str):
            self._input_files.append(content)
            self._on_disk = False
        else:
            raise ValueError(ERROR_MSG)

    def __call__(self, *args, **kwargs):
        """
        Just allows us to do Corpert(**kwargs)()
        """
        return self.run(*args, **kwargs)

    def _preprocess_labels(self, config, files):
        labels = dict()  # {layer: {attribute: {label1: None, label2: None, ...}}}
        output_path = self.output or "."
        for layer_name, layer_attrs in config["layer"].items():
            lname = layer_name.lower()
            if lname in {x.lower() for x in config["firstClass"].values()}:
                continue
            for attr_name, attr_values in layer_attrs.get("attributes", {}).items():
                if attr_values.get("type") != "labels":
                    continue
                aname = attr_name.lower()
                layer_file = get_file_from_base(layer_name, files)
                if not layer_file:
                    print(
                        f"Warning: {layer_name}->{attr_name} is of type labels but no file could be found for {layer_name}"
                    )
                    continue
                layer_attr_labels = {}
                with open(layer_file, "r", encoding="utf-8") as input:
                    found_comma = False
                    headers = []
                    while line := input.readline():
                        cells = parse_csv(line)
                        if not headers:
                            headers = cells
                            if aname not in [c.lower() for c in cells]:
                                print(
                                    f"Warning: could not find a column named {attr_name} in {layer_file}"
                                )
                                break
                            continue
                        unsplit_labels = next(
                            cells[n]
                            for n, h in enumerate(headers)
                            if h.lower() == aname
                        )
                        found_comma = found_comma or ("," in unsplit_labels)
                        split_labels = {
                            l.strip(): True for l in unsplit_labels.split(",")
                        }
                        layer_attr_labels.update(split_labels)
                if not found_comma:
                    print(
                        f"Warning: no comma found in any of the labels, did you forget to separate your labels with commas?"
                    )
                if layer_attr_labels:
                    labels[layer_name] = labels.get(layer_name, {})
                    labels[layer_name][attr_name] = layer_attr_labels
                    # output_fn = os.path.join(output_path, f"{lname}_{aname}.csv")
                    output_fn = os.path.join(output_path, f"{lname}_labels.csv")
                    if os.path.exists(output_fn):
                        print(
                            f"Warning: file {output_fn} already exists -- overwriting it"
                        )
                    with open(output_fn, "w", encoding="utf-8") as output:
                        output.write(to_csv(["bit", "label"]))
                        for n, lab in enumerate(layer_attr_labels):
                            output.write(to_csv([str(n), lab]))
        return labels

    def _prepare_aligned_entity_dict(
        self, filename, layer_name, config, labels
    ) -> tuple[dict[str, list[str]], list[str]]:
        """
        Read the table file corresponding to the aligned entity
        and return prepared rows + column names
        """
        print(f"Processing {filename}...")
        ret: dict[str, list[str]] = dict()
        ae_col_names: list[str] = []
        lname: str = layer_name.lower()
        layer_config: dict = config["layer"].get(layer_name, {})
        layer_attributes: dict = layer_config.get("attributes", {})
        output_path: str = self.output or "."
        lookup_tables: dict[str, LookupTable] = {}
        categorical_values: dict[str, set[str]] = {}

        file_content = read_csv(filename)
        # Prepare the column names
        #   ae_col_names are the columns in the (future) output file
        #   col_names are the columns (minus ID) from the input file
        ae_col_names = [f"{lname}_id"]
        col_names = [c.strip() for c in file_content.columns]
        for n, cn in enumerate(col_names):
            if n == 0:
                continue
            attribute_props = layer_attributes.get(cn, None)
            assert attribute_props is not None, ReferenceError(
                f"Attribute {cn} not found for entity {layer_name}"
            )
            col_name = cn.lower()
            if attribute_props.get("type", "") == "text":
                ae_col_names.append(col_name + "_id")
                lookup_tables[col_name] = LookupTable(
                    lname, col_name, output_path, config
                )
            else:
                ae_col_names.append(col_name)
        if is_char_anchored(layer_config, config):
            ae_col_names.append("char_range")
        if is_time_anchored(layer_config, config):
            ae_col_names.append("frame_range")

        # Process the rows
        for _, cols in file_content.iterrows():
            prepared_cols = []
            id = ""
            for n, col_name in enumerate(col_names):
                col: str = "" if isna(cols[col_name]) else str(cols[col_name])
                if n == 0:
                    id = col
                    continue
                attr_name = next(
                    (
                        x
                        for x in layer_attributes
                        if x.lower() == col_name or x.lower() + "_id" == col_name
                    ),
                    col_name,
                )
                ctype = layer_attributes.get(attr_name, {}).get("type")
                if ctype == "text":
                    # Create a lookup table if it doesn't exist
                    lookup_table: LookupTable = lookup_tables[col_name]
                    col = lookup_table.get_id(col)
                elif ctype == "labels":
                    current_labels = {l.strip() for l in col.split(",")}
                    attr_labels = labels.get(layer_name, {}).get(attr_name, {})
                    indices = {
                        n for n, lab in enumerate(attr_labels) if lab in current_labels
                    }
                    bits = [int(n in indices) for n in range(len(attr_labels))]
                    col = "".join([str(b) for b in bits])
                elif ctype == "categorical":
                    if col_name not in categorical_values:
                        categorical_values[col_name] = set()
                    categorical_values[col_name].add(col)

                prepared_cols.append(col)

            ret[id] = prepared_cols

        # List the categorical values in the config
        for cn, cv in categorical_values.items():
            config["layer"][layer_name]["attributes"][cn]["values"] = [
                Sentence._esc(v) for v in cv
            ]
        return (ret, ae_col_names)

    def _detect_format_from_string(self, content):
        """
        todo: this, but accurately!
        """
        if "sent_id = " in content:
            return "conllu"
        return "json"

    def _determine_format(self, filepath):
        """
        Deduce format from filepath, or from data string if need be
        """
        if os.path.isfile(filepath):
            if filepath.endswith((".conllu", ".conll")):
                return "conllu"
        elif isinstance(filepath, str):
            return self._detect_format_from_string(filepath)
        raise ValueError(ERROR_MSG)

    def _write_json(self, combined):
        """
        Create JSON file(s) depending on combine setting
        """
        if self._combine:
            with open(self.output, "w", encoding="utf-8") as fo:
                json.dump(combined, fo, indent=4, sort_keys=False)
        else:
            for path, data in combined.items():
                fixed_path = os.path.join(self.output, os.path.relpath(path))
                if not os.path.isdir(os.path.dirname(fixed_path)):
                    os.makedirs(os.path.dirname(fixed_path))
                with open(fixed_path, "w", encoding="utf-8") as fo:
                    data = {path: data}
                    json.dump(data, fo, indent=4, sort_keys=False)

    def _write_to_file(self, filename, data):
        """
        Helper: write data to filename
        """
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        with open(filename, "w", encoding="utf-8") as fo:
            fo.write(data)

    def _setup_filters(self):
        """
        If user wants to do lua/python filtering, we prepare things here
        """
        if self._lua_filter:
            # import lupa
            from lupa import LuaRuntime

            self._lua = LuaRuntime(unpack_returned_tuples=True)
        elif self._filter:
            pass

    def _apply_lua_filter(self, content):
        """
        Run user's lua function on the JSON data for a file
        """
        with open(self._lua_filter, "r", encoding="utf-8") as fo:
            script = fo.read()
        func = self._lua.eval(script)
        return func(content)

    def _apply_filter(self, content):
        """
        Run user's python function on the JSON data for a file
        """
        with open(self._filter, "r", encoding="utf-8") as fo:
            script = fo.read()
        return exec(script, {}, {"content": content})

    def run(self):
        """
        The main routine: read in all input files and print/write them
        """
        self._setup_filters()

        ignore_files = set()
        json_obj = None
        json_file = next(
            (
                os.path.join(self._path, f)
                for f in os.listdir(self._path)
                if f.endswith(".json")
            ),
            "",
        )
        if os.path.isfile(json_file):
            ignore_files.add(json_file)
            with open(json_file, "r", encoding="utf-8") as jsf:
                json_obj = json.loads(jsf.read())
        else:
            json_obj = default_json(
                next(reversed(self._path.split(os.path.sep))) or "Anonymous Project"
            )
        parent_dir = os.path.dirname(__file__)
        schema_path = os.path.join(parent_dir, "data", "lcp_corpus_template.json")
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            validate(json_obj, json.loads(schema_file.read()))
            print("validated json schema")

        output_path = self.output or "."
        os.makedirs(
            output_path, exist_ok=True
        )  # create the output directory if it doesn't exist

        aligned_entities = {}
        aligned_entities_segment = {}
        firstClass = json_obj.get("firstClass", {})
        for l in firstClass.values():
            assert l in json_obj.get("layer", {}), ReferenceError(
                f"'{l}' is declared in 'firstClass' but could not be found in 'layer'."
            )

        token_is_char_anchored = is_char_anchored(
            json_obj.get("layer", {}).get(firstClass["token"], {}), json_obj
        )
        # Check the existence of time-anchored files and add them to ignore_files
        for layer, properties in json_obj.get("layer", {}).items():
            if (
                not is_time_anchored(properties, json_obj)
                or layer in firstClass.values()
            ):
                continue
            fn = get_file_from_base(layer, os.listdir(self._path))
            fpath = os.path.join(self._path, fn)
            assert os.path.exists(fpath), FileNotFoundError(
                f"Could not find a file named '{fn}' in {self._path} for time-anchored layer '{layer}'"
            )
            ignore_files.add(fpath)
        # Detect the global attributes files and exclude them from the list of files to process
        for glob_attr in json_obj.get("globalAttributes", {}):
            stem_name = f"global_attribute_{glob_attr}"
            filename = get_file_from_base(stem_name, os.listdir(self._path))
            source = os.path.join(self._path, filename)
            ignore_files.add(source)
            assert os.path.exists(source), FileExistsError(
                f"No file named '{filename}' found for global attribute '{glob_attr}'"
            )
            shutil.copy(source, os.path.join(output_path, filename))

        labels = self._preprocess_labels(json_obj, self._input_files)
        for layer_name, attributes in labels.items():
            for attribute_name, attribute_labels in attributes.items():
                json_obj["layer"][layer_name]["attriubtes"][attribute_name][
                    "nlabels"
                ] = len(attribute_labels)

        # Process the input files that are not at the token, segment or document level
        for layer, properties in json_obj.get("layer", {}).items():
            if layer in firstClass.values():
                continue
            # Process entities that are spans containing sub-entities (eg. named entities or topics)
            if (
                not token_is_char_anchored
                or properties.get("abstract")
                or properties.get("layerType") != "span"
                or properties.get("contains", "")
                not in (firstClass["token"], firstClass["segment"])
            ):
                continue
            layer_file = os.path.join(
                self._path, get_file_from_base(layer, os.listdir(self._path))
            )
            assert layer_file, FileExistsError(
                f"Could not find a reference file for entity type '{layer}'"
            )
            ignore_files.add(layer_file)
            with open(layer_file, "r", encoding="utf-8") as f:
                cols = [x.lower() for x in parse_csv(f.readline())]
                for a in properties.get("attributes", {}):
                    assert a.lower() in cols, ReferenceError(
                        f"No column found for attribute '{a}' in {layer_file}"
                    )
            if properties["contains"] == firstClass["token"]:
                ae_table, ae_col_names = self._prepare_aligned_entity_dict(
                    layer_file, layer, json_obj, labels
                )
                aligned_entities[layer.lower()] = {
                    "fn": layer_file,
                    "properties": properties,
                    "refs": ae_table,
                    "col_names": ae_col_names,
                }
            else:
                aes_table, aes_col_names = self._prepare_aligned_entity_dict(
                    layer_file, layer, json_obj, labels
                )
                aligned_entities_segment[layer.lower()] = {
                    "fn": layer_file,
                    "properties": properties,
                    "refs": aes_table,
                    "col_names": aes_col_names,
                }
        parser = None
        # Process the remaining input files
        doc_files = [
            f
            for f in self._input_files
            if (
                os.path.isfile(f)
                and f not in ignore_files
                and os.path.basename(f) != "meta.json"
                # discard files named like layer names
                and Path(f).stem.lower()
                not in {k.lower() for k in json_obj.get("layer", {})}
            )
        ]
        nfiles = len(doc_files)
        start_time_input_files = time()
        for nfile, filepath in enumerate(doc_files, start=1):
            elapsed_time = time() - start_time_input_files
            print(
                "input file",
                filepath,
                f" ({nfile}/{nfiles}; elapsed {round(elapsed_time, 2)}s;",
                f"remaining {round((elapsed_time / nfile) * (nfiles - nfile))}s)",
            )
            parser = parser or PARSERS[self._determine_format(filepath)](
                config=json_obj, labels=labels
            )
            print(filepath)
            try:
                # First pass: check that the file has some content
                with open(filepath, "r", encoding="utf-8") as f:
                    has_content = False
                    while line := f.readline():
                        line = line.strip()
                        if line.startswith("#") or not line:
                            continue
                        has_content = True
                        break
                    assert has_content, AssertionError("No conllu lines to process")
                with open(filepath, "r", encoding="utf-8") as f:
                    parser.generate_upload_files_generator(
                        f,
                        path=output_path,
                        default_doc={"name": os.path.basename(filepath)},
                        config=json_obj,
                        aligned_entities=aligned_entities,
                        aligned_entities_segment=aligned_entities_segment,
                    )
            except Exception as err:
                print("Could not process", filepath, ": ", err)
                traceback.print_exc()
        parser.close_upload_files(path=output_path)
        # Process time-anchored extra layers
        for layer, properties in json_obj.get("layer", {}).items():
            if (
                not is_time_anchored(properties, json_obj)
                or layer in firstClass.values()
            ):
                continue
            fn = get_file_from_base(layer, os.listdir(self._path))
            attributes = properties.get("attributes", {})
            input_col_names = []
            doc_id_idx = 0
            start_idx = 0
            end_idx = 0
            output_fn = os.path.join(output_path, fn)
            assert not os.path.exists(output_fn), FileExistsError(
                f"The output file '{output_fn}' already exists."
            )
            with (
                open(os.path.join(self._path, fn), "r", encoding="utf-8") as input_file,
                open(output_fn, "w", encoding="utf-8") as output_file,
            ):
                while input_line := input_file.readline():
                    input_cols = parse_csv(input_line)
                    output_cols = []
                    if not input_col_names:
                        input_col_names = input_cols
                        output_cols = [
                            c
                            for c in input_col_names
                            if c not in ("doc_id", "start", "end")
                        ]
                        assert "doc_id" in input_col_names, IndexError(
                            f"No column named 'doc_id' found in {fn}"
                        )
                        assert "start" in input_col_names, IndexError(
                            f"No column named 'start' found in {fn}"
                        )
                        assert "end" in input_col_names, IndexError(
                            f"No column named 'end' found in {fn}"
                        )
                        doc_id_idx = input_cols.index("doc_id")
                        start_idx = input_cols.index("start")
                        end_idx = input_cols.index("end")
                        output_cols.append("frame_range")
                    else:
                        output_cols = [
                            c.strip()
                            for n, c in enumerate(input_cols)
                            if n not in (doc_id_idx, start_idx, end_idx)
                        ]
                        for a, av in attributes.items():
                            if av.get("type") != "categorical" or av.get("isGlobal"):
                                continue
                            col_n = next(
                                (
                                    n
                                    for n, cn in enumerate(input_col_names)
                                    if cn == a.lower()
                                ),
                                None,
                            )
                            if col_n is None:
                                continue
                            av["values"] = av.get("values", [])
                            value_to_add = input_cols[col_n].strip()
                            if value_to_add not in av["values"]:
                                av["values"].append(value_to_add)
                        doc_frames = parser.doc_frames[str(input_cols[doc_id_idx])]
                        times = [float(input_cols[x]) for x in (start_idx, end_idx)]
                        start, end = [
                            int(times[n] * 25.0) + doc_frames[0] for n in (0, 1)
                        ]
                        if end <= start:
                            end = int(start) + 1
                        output_cols.append(f"[{start},{end})")
                    output_file.write(to_csv(output_cols))

        print(f"outfiles written to '{self.output}'.")
        json_str = json.dumps(json_obj, indent=4)
        json_path = os.path.join(output_path, "meta.json")
        open(json_path, "w", encoding="utf-8").write(json_str)
        # print(f"\n{json_str}\n")
        print(
            f"A default meta.json file with the structure above was automatically generated at '{json_path}' for the current corpus."
        )
        print(f"Please review it and make any changes as needed in a text editor.")


def run() -> None:
    kwargs = _parse_cmd_line()
    Corpert(**kwargs).run()


if __name__ == "__main__":
    """
    When the user calls the script directly in command line, this is what we do
    """
    run()
