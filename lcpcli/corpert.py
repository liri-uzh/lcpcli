import json
import os
import re

from .cli import _parse_cmd_line
from .conllu_builder import process_files
from .utils import default_json, find_config_file, yes_no_input

ERROR_MSG = """
Unrecognized input format.
Note: The converter currently supports the following formats:
.conllu, .conll
"""


class Corpert:

    def __init__(
        self,
        content,
        output=None,
        extension=None,
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

    def run(self, conll_only: bool = False, overwite_output: bool = False):
        """
        The main routine: read in all input files and print/write them
        """

        assert self.output and os.path.isdir(self.output), FileNotFoundError(
            f"The output directory {self.output} is invalid."
        )

        if not overwite_output and any(
            f.endswith((".json", ".csv")) for f in os.listdir(self.output)
        ):
            print(
                f"The destination folder {self.output} contains some JSON and/or CSV files which this operation might overwrite. Do you want to proceed?"
            )
            if not yes_no_input():
                print("Aborting the conversion operation.")
                return

        ignore_files = set()
        json_obj = None
        try:
            json_file = find_config_file(self._path)
            ignore_files.add(json_file)
            with open(json_file, "r", encoding="utf-8") as jsf:
                json_obj = json.loads(jsf.read())
            print(f"Validated the JSON configuration file {json_file}")
        except:
            json_obj = default_json(
                next(reversed(self._path.split(os.path.sep))) or "Unnamed corpus"
            )
            print("Using a default json configuration")

        output_path = self.output or "."
        os.makedirs(
            output_path, exist_ok=True
        )  # create the output directory if it doesn't exist

        # List the input files
        doc_files = [
            str(f)
            for f in self._input_files
            if (
                os.path.isfile(f)
                and f not in ignore_files
                and not str(f).endswith(".json")
            )
        ]

        if (
            not conll_only
            and any(f.lower().endswith((".conllu", ".conll")) for f in doc_files)
            and any(not f.lower().endswith((".conllu", ".conll")) for f in doc_files)
        ):
            print(
                f"The input folder ({self._path}) contains both files with a CoNLL extension and files with a different extension."
            )
            print("Ignore the files with a non-CoNLL extension?")
            if yes_no_input():
                doc_files = [
                    f for f in doc_files if f.lower().endswith((".conll", ".conllu"))
                ]

        corpus = process_files(doc_files, json_obj.get("meta", {}))
        print(f"Writing files to '{self.output}'...")
        corpus.make(self.output)

        print(f"Output files written to '{self.output}'.")
        print(
            f"A JSON configuration file was placed in '{self.output}' for the current corpus."
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
