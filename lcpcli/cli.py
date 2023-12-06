import argparse

from typing import Any

BOOL_KWARGS: dict[str, Any]

try:
    BOOL_KWARGS = {"type": bool, "action": argparse.BooleanOptionalAction}
except (ImportError, AttributeError):
    BOOL_KWARGS = {"action": "store_true"}


def _parse_cmd_line():
    """
    Helper for parsing CLI call and displaying help message
    """
    parser = argparse.ArgumentParser(description="Convert and upload corpus to LCP")
    
    # CORPERT
    parser.add_argument(
        "-i", "--input", type=str, required=False, help="Input file path"
    )
    parser.add_argument("-o", "--output", type=str, help="Output file path")
    parser.add_argument(
        "-m",
        "--mode",
        type=str,
        nargs="?",
        choices=["normal", "upload"],
        default="normal",
        help="LCP upload ('upload') or not ('normal', default)")
    parser.add_argument(
        "-e", "--extension", type=str, help="Output format when output is a directory"
    )
    parser.add_argument(
        "-f", "--filter", required=False, type=str, help="Path to a Python filter file"
    )
    parser.add_argument(
        "-u", "--lua-filter", required=False, type=str, help="Path to a Lua filter file"
    )
    parser.add_argument(
        "-x",
        "--combine",
        required=False,
        type=bool,
        default=False,
        help="Combine into single file?",
        # action=argparse.BooleanOptionalAction,
    )
    
    # LCPUPLOAD
    parser.add_argument(
        "-c",
        "--corpus",
        type=str,
        required=False,
        help="Corpus path (either a directory or a zip/7z/tar/tar.gz/tar.xz archive)",
    )
    parser.add_argument(
        "-k",
        "--api-key",
        type=str,
        required=False,
        help="API key",
    )
    parser.add_argument(
        "-s",
        "--secret",
        type=str,
        required=False,
        help="API key secret",
    )
    parser.add_argument(
        "-p",
        "--project",
        type=str,
        required=False,
        help="Project the corpus will be uploaded into",
    )
    parser.add_argument(
        "-j",
        "--json",
        type=str,
        required=False,
        help="JSON template filepath or raw JSON string. If not provided, the first JSON file found in the corpus data will be used.",
    )
    parser.add_argument(
        "-l",
        "--live",
        required=False,
        default=False,
        help="Use live system? If false, use test system.",
        **BOOL_KWARGS
    )
    parser.add_argument(
        "-v",
        "--vian",
        required=False,
        default=False,
        help="Upload to VIAN instead of LCP?",
        **BOOL_KWARGS
    )
    
    kwargs = vars(parser.parse_args())
    kwargs["content"] = kwargs.pop("input", "")
    kwargs["template"] = kwargs.pop("json", False)
    return kwargs
