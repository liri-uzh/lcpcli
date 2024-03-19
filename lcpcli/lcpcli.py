import os
import shutil

from corpert import Corpert
from lcp_upload import lcp_upload

from inspect import signature

class Lcpcli:

    def __init__(
        self,
        *args,
        **kwargs
    ):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        """
        Just allows us to do Lcpcli(**kwargs)()
        """
        return self.run(*args, **kwargs)

    def run(self):

        upload = self.kwargs.get("api_key") and self.kwargs.get("secret")
        corpert = None

        if self.kwargs.get("content"):
            self.kwargs['content'] = os.path.abspath(self.kwargs['content'])

            corpert_signature = signature(Corpert.__init__)
            corpert_kwargs = {k:v for k,v in self.kwargs.items() if k in corpert_signature.parameters}
            corpert = Corpert(**corpert_kwargs)

            corpert.run()

        if upload:

            if corpert and self.kwargs.get("mode", "") == "upload":
                path = self.kwargs.get("output", os.path.dirname(corpert._path))

                assert next((f for f in os.listdir(path) if f.endswith(".json")), None), FileNotFoundError(f"No JSON file found in {path}")

                output_dir = os.path.join(path,"_upload")
                if not os.path.isdir(output_dir):
                    os.mkdir(output_dir)
                json = ""
                for f in os.listdir(path):
                    if f.endswith(".csv"):
                        os.rename(os.path.join(path,f),os.path.join(output_dir,f))
                    elif f.endswith(".json") and not json:
                        shutil.copy(os.path.join(path,f), os.path.join(output_dir,f))
                self.kwargs["corpus"] = output_dir
                print("corpert._path", output_dir)

            assert self.kwargs.get("corpus"), SyntaxError("No corpus found to upload")

            lcp_upload_signature = signature(lcp_upload)
            lcp_upload_kwargs = {k:v for k,v in self.kwargs.items() if k in lcp_upload_signature.parameters}

            print("lcp_upload_kwargs", lcp_upload_kwargs)

            lcp_upload(**lcp_upload_kwargs)


if __name__ == "__main__":
    """
    When the user calls the script directly in command line, this is what we do
    """
    from .cli import _parse_cmd_line

    kwargs = _parse_cmd_line()
    Lcpcli(**kwargs).run()
