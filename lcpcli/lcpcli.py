import os
import shutil

from collections.abc import Callable
from inspect import signature
from typing import Any

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
Use `lcpcli -i {input_path} -o {output_path} -m upload` to preprocess the data,
then `lcpcli -c {output_path} -k $API_KEY -s $API_SECRET -p $PROJECT_NAME --live` to upload the corpus to LCP"""
            )
            return None

        upload = self.kwargs.get("api_key") and self.kwargs.get("secret")
        corpert: Corpert | None = None

        if cont := self.kwargs.get("content"):
            self.kwargs["content"] = os.path.abspath(cont)
            corpert = Corpert(**self._get_kwargs(Corpert.__init__))
            corpert.run()

        if not upload:
            print("No upload key or secret passed, exiting now.")
            return None

        if corpert and self.kwargs.get("mode", "") == "upload":
            path = self.kwargs.get("output", os.path.dirname(corpert._path))

            if not any(i.endswith(".json") for i in os.listdir(path)):
                raise FileNotFoundError(f"No JSON file found in {path}")

            output_dir = os.path.join(path, "_upload")
            os.makedirs(output_dir, exist_ok=True)
            json = ""
            for f in os.listdir(path):
                if f.endswith((".csv", ".tsv")):
                    os.rename(os.path.join(path, f), os.path.join(output_dir, f))
                elif f.endswith(".json") and not json:
                    shutil.copy(os.path.join(path, f), os.path.join(output_dir, f))
            self.kwargs["corpus"] = output_dir

        if not self.kwargs.get("corpus"):
            raise ValueError("No corpus found to upload")

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
