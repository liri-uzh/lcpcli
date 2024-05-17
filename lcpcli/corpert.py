import codecs
import json
import os
import shutil

from .parsers.conllu import CONLLUParser
from .parsers.vert import VERTParser
from .parsers.tei import TEIParser
from .parsers.json import JSONParser

from .cli import _parse_cmd_line
from .utils import default_json

from jsonschema import validate
from pathlib import Path

# map between extensions and parsers
PARSERS = {
    "conllu": CONLLUParser,
    "vert": VERTParser,
    "xml": TEIParser,
    "tei": TEIParser,
    "json": JSONParser,
}

ERROR_MSG = """
Unrecognized input format.
Note: The converter currently supports the following formats:
.conllu, .xml (TEI), .json and .vert.
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
        mode=None,
        **kwargs,
    ):
        """
        path (str): path or string of content
        combine (bool): create single output file?
        """
        self.output = os.path.abspath(output) if output else None
        self._output_format = None
        self.mode = mode
        if extension:
            self._output_format = extension
        elif self.output and self.output.endswith(
            (".json", ".xml", ".conllu", ".vert", ".tei")
        ):
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
            for root, dirs, files in os.walk(content):
                for file in files:
                    fullpath = os.path.join(root, file)
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

    def _detect_format_from_string(self, content):
        """
        todo: this, but accurately!
        """
        if "sent_id = " in content:
            return "conllu"
        elif "<xml" in content:
            return "xml"
        elif "<s sent_id" in content:
            return "vert"
        return "json"

    def _determine_format(self, filepath):
        """
        Deduce format from filepath, or from data string if need be
        """
        if os.path.isfile(filepath):
            if filepath.endswith(".conllu"):
                return "conllu"
            elif filepath.endswith(".vert"):
                return "vert"
            elif filepath.endswith(".xml"):
                return "xml"
            elif filepath.endswith(".json"):
                return "json"
        elif isinstance(filepath, str):
            return self._detect_format_from_string(filepath)
        raise ValueError(ERROR_MSG)

    def _write_json(self, combined):
        """
        Create JSON file(s) depending on combine setting
        """
        if self._combine:
            with open(self.output, "w") as fo:
                json.dump(combined, fo, indent=4, sort_keys=False)
        else:
            for path, data in combined.items():
                fixed_path = os.path.join(self.output, os.path.relpath(path))
                if not os.path.isdir(os.path.dirname(fixed_path)):
                    os.makedirs(os.path.dirname(fixed_path))
                with open(fixed_path, "w") as fo:
                    data = {path: data}
                    json.dump(data, fo, indent=4, sort_keys=False)

    def _write_to_file(self, filename, data):
        """
        Helper: write data to filename
        """
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        with open(filename, "w") as fo:
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
        with open(self._lua_filter, "r") as fo:
            script = fo.read()
        func = self._lua.eval(script)
        return func(content)

    def _apply_filter(self, content):
        """
        Run user's python function on the JSON data for a file
        """
        with open(self._filter, "r") as fo:
            script = fo.read()
        return exec(script, {}, {"content": content})

    def run(self):
        """
        The main routine: read in all input files and print/write them
        """
        combined = {}
        self._setup_filters()
        # sents = []
        # docs = []

        if self.mode == "upload":
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
                with open(json_file, "r") as jsf:
                    json_obj = json.loads(jsf.read())
            else:
                json_obj = default_json(
                    next(reversed(self._path.split(os.path.sep))) or "Anonymous Project"
                )
            parent_dir = os.path.dirname(__file__)
            schema_path = os.path.join(parent_dir, "data", "lcp_corpus_template.json")
            with open(schema_path) as schema_file:
                validate(json_obj, json.loads(schema_file.read()))
                print("validated json schema")

            aligned_entities = {}
            aligned_entities_segment = {}
            firstClass = json_obj.get("firstClass", {})
            # Detect the global attributes files and exclude them from the list of files to process
            for glob_attr in json_obj.get("globalAttributes", {}):
                filename = f"global_attribute_{glob_attr}.csv"
                source = os.path.join(self._path, filename)
                ignore_files.add(source)
                if os.path.exists(source):
                    shutil.copy(source, os.path.join(self.output or "./", filename))
            # Parse the input files that are not at the token, segment or document level
            for layer, properties in json_obj.get("layer", {}).items():
                if layer in firstClass.values():
                    continue
                if (
                    properties.get("abstract", False) == False
                    and properties.get("layerType", "") == "span"
                    and properties.get("contains", "")
                    in (firstClass["token"], firstClass["segment"])
                    and json_obj.get("layer", {})
                    .get(firstClass["token"], {})
                    .get("anchoring", {})
                    .get("stream", False)
                ):
                    layerFile = next(
                        (
                            f
                            for f in self._input_files
                            if Path(f).stem.lower() == layer.lower()
                        ),
                        "",
                    )
                    assert layerFile, FileExistsError(
                        f"Could not find a reference file for entity type '{layer}'"
                    )
                    ignore_files.add(layerFile)
                    with open(layerFile, "r") as f:
                        cols = [x.lower() for x in f.readline().split()]
                        for a in properties.get("attributes", {}):
                            assert a.lower() in cols, ReferenceError(
                                f"No column found for attribute '{a}' in {layerFile}"
                            )
                    if properties["contains"] == firstClass["token"]:
                        aligned_entities[layer.lower()] = {
                            "fn": layerFile,
                            "properties": properties,
                        }
                    else:
                        aligned_entities_segment[layer.lower()] = {
                            "fn": layerFile,
                            "properties": properties,
                        }
            parser = None
            # Parse the remaining input files
            for filepath in self._input_files:
                if filepath in ignore_files:
                    continue
                fn_before_ext = Path(filepath).stem
                if fn_before_ext.lower() in {
                    k.lower() for k in json_obj.get("layer", {})
                }:
                    continue
                print("input file", filepath)
                if not os.path.isfile(filepath):
                    print(f"Not a file: ignoring '{filepath}'")
                    continue
                if os.path.basename(filepath) == "meta.json":
                    continue
                parser = parser or PARSERS[self._determine_format(filepath)](
                    config=json_obj
                )
                print(filepath)
                with open(filepath, "r") as f:
                    parser.generate_upload_files_generator(
                        f,
                        path=self.output or "./",
                        default_doc={"name": os.path.basename(filepath)},
                        config=json_obj,
                        aligned_entities=aligned_entities,
                        aligned_entities_segment=aligned_entities_segment,
                    )
            parser.close_upload_files(
                path=self.output or "./",
            )
            # Process time-anchored extra layers
            for layer, properties in json_obj.get("layer", {}).items():
                if (
                    not properties.get("anchoring", {}).get("time", False)
                    or layer in json_obj["firstClass"].values()
                ):
                    continue
                fn = f"{layer.lower()}.csv"
                assert os.path.exists(os.path.join(self._path, fn)), FileExistsError(
                    f"Could not find a file named '{fn}' in {self._path} for time-anchored layer '{layer}'"
                )
                output_path = self.output or "./"
                input_col_names = []
                doc_id_idx = 0
                start_idx = 0
                end_idx = 0
                with open(os.path.join(self._path, fn), "r") as input_file:
                    with open(os.path.join(output_path, fn), "w") as output_file:
                        while True:
                            input_line = input_file.readline()
                            if not input_line:
                                break
                            input_cols = input_line.split("\t")
                            output_cols = []
                            if not input_col_names:
                                input_col_names = input_cols
                                output_cols = [
                                    c.strip()
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
                                doc_frames = parser.doc_frames[
                                    str(input_cols[doc_id_idx])
                                ]
                                times = [
                                    float(input_cols[x]) for x in (start_idx, end_idx)
                                ]
                                start, end = [
                                    str(int(times[n] * 25.0) + doc_frames[n])
                                    for n in (0, 1)
                                ]
                                output_cols.append(f"[{start},{end})")
                            output_file.write("\t".join(output_cols) + "\n")

            print(f"outfiles written to '{self._path}'.")
            json_str = json.dumps(json_obj, indent=4)
            json_path = os.path.join(self.output or ".", "meta.json")
            open(json_path, "w").write(json_str)
            print(f"\n{json_str}\n")
            print(
                f"A default meta.json file with the structure above was automatically generated at '{json_path}' for the current corpus."
            )
            print(f"Please review it and make any changes as needed in a text editor.")
            print(
                f"Once the file contains the proper information, press any key to proceed."
            )
            input()

        else:
            format = (self._output_format or "").lstrip(".")

            for filepath in self._input_files:
                print("input file", filepath)
                if os.path.isfile(filepath):
                    parser = PARSERS[self._determine_format(filepath)]()
                else:
                    parser = self._detect_format_from_string(filepath)

                reader = parser.parse_generator(codecs.open(filepath, "r", "utf8"))
                for sentence in parser.write_generator(reader):
                    print("writing", sentence)

                continue
                if self._on_disk:
                    with codecs.open(filepath, "r", "utf8") as fo:
                        content = fo.read()
                else:
                    content = filepath

                understood = parser.parse(content)
                if self._filter:
                    understood = self._apply_filter(understood)
                if self._lua_filter:
                    understood = self._apply_lua_filter(understood)

                if len(understood) == 1:
                    combined[filepath] = next(v for _, v in understood.items())
                else:
                    # if 'documents' in understood:
                    for doc, v in understood.items():
                        subfilepath = os.path.join(filepath, f"{doc}.{format}")
                        combined[subfilepath] = v
                # else:
                #     combined[filepath] = understood

            return

            if not self.output:
                print(json.dumps(combined, indent=4, sort_keys=False))
                return combined
            elif self._output_format.endswith("json"):
                self._write_json(combined)
                return
            else:
                parser = PARSERS[format]()
                if not self._combine:
                    # print("combined", combined)
                    for path, data in combined.items():
                        # text_id = os.path.splitext(os.path.basename(path))[0]
                        meta = {"id": path, **data.get("meta", {})}
                        formatted = parser.write(
                            data.get("sentences", {}), path, combine=False, meta=meta
                        )
                        # fixed_path = os.path.join(self.output, os.path.relpath(path))
                        fixed_path = os.path.join(self.output, os.path.basename(path))
                        # print(f"writing {len(formatted)} chars to {fixed_path}")
                        self._write_to_file(fixed_path, formatted)
                    return
                else:
                    if len(combined) == 1:
                        path, data = combined.popitem()
                        meta = {"id": path, **data.get("meta", {})}
                        formatted = parser.write(
                            data.get("sentences", {}), path, combine=False, meta=meta
                        )
                    else:
                        formatted = parser.combine(combined)
                    self._write_to_file(self.output, formatted)
                    return

            raise ValueError(ERROR_MSG.replace("input", "output"))


def run() -> None:
    kwargs = _parse_cmd_line()
    Corpert(**kwargs).run()


if __name__ == "__main__":
    """
    When the user calls the script directly in command line, this is what we do
    """
    run()
