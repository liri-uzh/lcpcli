import os
import shutil

from collections.abc import Callable
from inspect import signature
from json import loads
from typing import Any

from .check_files import Checker
from .corpert import Corpert
from .lcp_upload import lcp_upload
from .cli import _parse_cmd_line


class Lcpcli:

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __new__(cls, *args, **kwargs):
        """
        Just allows us to do Lcpcli(**kwargs)
        """
        inst = super().__new__(cls)
        inst.__init__(*args, **kwargs)
        return inst.run()

    def _get_kwargs(self, func: Callable) -> dict[str, Any]:
        """
        Helper to get the arguments for `func` from self.kwargs
        """
        allowed = set(signature(func).parameters)
        return {k: v for k, v in self.kwargs.items() if k in allowed}

    def run(self) -> None:

        if example_destination := self.kwargs.get("example"):
            if not os.path.isdir(example_destination):
                raise FileNotFoundError(
                    f"Path '{example_destination}' is not a valid folder destination"
                )
            parent_dir = os.path.dirname(__file__)
            example_path = os.path.join(parent_dir, "data", "free_video_corpus")
            full_destination = os.path.join(example_destination, "free_video_corpus")
            shutil.copytree(example_path, full_destination)
            input_path = os.path.join(full_destination, "input")
            output_path = os.path.join(full_destination, "output")
            print(
                f"""Example data files copied to {full_destination}.
Use `lcpcli -i {input_path} -o {output_path}` to preprocess the data,
then `lcpcli -c {output_path} -k $API_KEY -s $API_SECRET -p $PROJECT_NAME --live` to upload the corpus to LCP"""
            )
            return None

        upload = self.kwargs.get("api_key") and self.kwargs.get("secret")
        corpert: Corpert | None = None

        if cont := self.kwargs.get("content"):
            self.kwargs["content"] = os.path.abspath(cont)
            corpert = Corpert(**self._get_kwargs(Corpert.__init__))
            corpert.run()

        if not upload and not self.kwargs["check_only"]:
            print("No upload key or secret passed, exiting now.")
            return None

        if corpert:
            path = self.kwargs.get("output", os.path.dirname(corpert._path))

            if not any(i.endswith(".json") for i in os.listdir(path)):
                raise FileNotFoundError(f"No JSON file found in {path}")

            print(
                f"Please review the content of the configuration file, then press any key to proceed."
            )
            input()

            output_dir = os.path.join(path, "_upload")
            os.makedirs(output_dir, exist_ok=True)
            json = ""
            for f in os.listdir(path):
                if f.endswith((".csv", ".tsv")):
                    os.rename(os.path.join(path, f), os.path.join(output_dir, f))
                elif f.endswith(".json") and not json:
                    shutil.copy(os.path.join(path, f), os.path.join(output_dir, f))
            if os.path.isdir(os.path.join(path, "media")):
                os.symlink(
                    os.path.join(path, "media"),
                    os.path.join(output_dir, "media"),
                    target_is_directory=True,
                )
            self.kwargs["corpus"] = output_dir

        if not self.kwargs.get("corpus"):
            raise ValueError("No corpus found to upload")

        json_file = next(
            (f for f in os.listdir(self.kwargs["corpus"]) if f.endswith(".json")), None
        )
        assert json_file, FileNotFoundError(
            f"Could not find a JSON configuration file in {self.kwargs['corpus']}"
        )
        conf: dict[str, Any] = loads(
            open(
                os.path.join(self.kwargs["corpus"], json_file), "r", encoding="utf-8"
            ).read()
        )
        checker = Checker(
            conf,
            quote=self.kwargs.get("quote") or '"',
            delimiter=self.kwargs.get("delimiter") or ",",
            escape=self.kwargs.get("escape") or None,
        )
        text_attrs: list[tuple[str, str]] = [
            (lay, attr)
            for lay, props in conf["layer"].items()
            for attr in {
                aname
                for aname, ameta in props.get("attributes", {}).items()
                if ameta.get("type") == "text"
            }
        ]
        no_index: set[tuple[str, str]] = set()
        callback: Callable = lambda c, h, f, *_: no_index.add(
            next(
                (
                    (lay, attr)
                    for lay, attr in text_attrs
                    if f.startswith(f"{lay}_{attr}.".lower())
                    and len(c[h.index(attr.lower())]) > 2000
                ),
                ("", ""),
            )
        )
        checker.run_checks(
            self.kwargs["corpus"], full=True, add_zero=False, callback=callback
        )
        self.kwargs["no_index"] = [
            [lay, attr] for lay, attr in no_index if lay and attr
        ]
        return lcp_upload(**self._get_kwargs(lcp_upload))


def run() -> None:
    """
    pyproject.toml likes a function callable entrypoint
    """
    Lcpcli(**_parse_cmd_line())


if __name__ == "__main__":
    """
    When the user calls the script directly in command line, this is what we do
    """
    run()
