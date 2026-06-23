#! /usr/bin/env python3

from __future__ import annotations


import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time

from collections.abc import Callable
from typing import Any, cast
from tusclient import client, uploader as tus_uploader

import requests

from tqdm import tqdm
from math import ceil, log2

from . import __version__
from .check_files import Checker
from .cli import _parse_cmd_line
from .utils import (
    find_config_file,
    default_json,
    get_file_from_base,
    is_valid_zip,
    COMPRESSED_EXTENSIONS,
)

# CREATE_URL = "https://lcp.test.linguistik.uzh.ch/create"
# UPLOAD_URL = "https://lcp.test.linguistik.uzh.ch/upload"
CREATE_URL = "https://lcp.linguistik.uzh.ch"
CREATE_URL_TEST = "http://localhost:9090"

VALID_EXTENSIONS = (
    "csv",
    "tsv",
)

AUDIOVIDEO_EXTENSIONS = ("mp3", "mp4", "wav", "ogg")
IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "bmp")

POST_SIZE_LIMIT = 10 * 1000000000  # in bytes


class CustomUploader(tus_uploader.Uploader):
    def __init__(self, *args, **kwargs):
        headers = kwargs.pop("headers", {})
        super().__init__(*args, **kwargs)
        metadata = headers.pop("Upload-Metadata")
        if metadata:
            self.metadata = metadata
        self.client.headers.update(headers)
        self.last_post_headers = None

    def _do_request(self):
        super()._do_request()
        try:
            self.last_post_headers = self.request.response_headers
        except:
            pass

    def upload(self, stop_at: int | None = None):
        super().upload(stop_at=stop_at)
        return self.last_post_headers


class CustomTusClient(client.TusClient):
    def uploader(self, *args, **kwargs):
        return CustomUploader(*args, client=self, **kwargs)


def post(*args, **kwargs):
    if "files" in kwargs:
        size = sum(os.path.getsize(f.name) for f in kwargs["files"].values())
        assert size < POST_SIZE_LIMIT, ConnectionRefusedError(
            f"Cannot send more than {POST_SIZE_LIMIT / 1000000}MB in one POST request"
        )
    return requests.post(*args, **kwargs)


def lcp_upload(
    corpus: str = "",
    api_key: str = "",
    template: str | None = "",
    secret: str = "",
    project: str | None = None,
    vian: bool = False,
    live: bool = False,
    provided_url: str = "",
    check_only: bool = False,
    n_batches: int = 10,
    delimiter: str = "",
    quote: str = "",
    escape: str = "",
    force_corpus_overwrite: bool = False,
    skip_check: bool = False,
) -> None:

    filt = None
    # delete_template = False
    template_data = None

    is_zip, is_valid = is_valid_zip(corpus)
    if is_zip:
        if not is_valid:
            return
        base = os.path.dirname(corpus)
        filt = os.path.basename(base)
    else:
        total_size = sum(
            [
                os.path.getsize(os.path.join(corpus, f))
                for f in os.listdir(corpus)
                if f.endswith((".csv", ".tsv"))
            ]
        )
        if total_size > 1e9:
            ext = "/".join(COMPRESSED_EXTENSIONS)
            print(
                f"Warning: upload of large uncompressed datasets may fail. "
                + f"Consider compressing {corpus} to {ext} and submitting the compressed archive."
            )
        base = corpus

    if template and not os.path.isfile(template):
        try:
            template_data = (
                json.loads(template) if isinstance(template, str) else template
            )
        except Exception:
            print(
                f"JSON template not understood. Please pass a filepath or valid JSON string."
            )
            return

    elif not template and os.path.isfile(corpus):
        print(
            "Warning: no template specified and corpus is not a directory. Looking inside archive..."
        )
        import tarfile
        from zipfile import ZipFile, is_zipfile
        from py7zr import SevenZipFile, is_7zfile

        ziptar: list[tuple[str, Callable, Callable, str, str]] = [
            (".zip", is_zipfile, ZipFile, "namelist", "r"),
            (".tar", tarfile.is_tarfile, tarfile.open, "getnames", "r"),
            (".tar.gz", tarfile.is_tarfile, tarfile.open, "getnames", "r:gz"),
            (".tar.xz", tarfile.is_tarfile, tarfile.open, "getnames", "r"),
            (".7z", is_7zfile, SevenZipFile, "getnames", "r"),
        ]
        found = False
        for ext, check, opener, method, mode in ziptar:
            if not corpus.endswith(ext):
                continue
            if not check(corpus):
                print(f"Problem with archive: {corpus}")
                return
            with opener(corpus, mode) as compressed:
                for f in getattr(compressed, method)():
                    if not f.endswith(".json"):
                        continue
                    try:
                        with tempfile.TemporaryDirectory() as dest:
                            if ext != ".7z":
                                compressed.extract(f, dest)
                            else:
                                compressed.extract(dest, [f])
                            template = find_config_file(dest)
                            template_data = json.loads(
                                open(template or "", "r", encoding="utf-8").read()
                            )
                            template = f
                            found = True
                            print(f"Using {f} from archive as template file...")
                        break
                    except:
                        pass
            if not found:
                print(f"Error: no JSON files found in archive: {corpus}")
                return
    elif not template and os.path.isdir(corpus):
        template = find_config_file(corpus)

    if not template_data:
        try:
            template_data = json.loads(
                open(template or "", "r", encoding="utf-8").read()
            )
        except:
            print("Cannot find a template file, using a default configuration")
            template_data = default_json(
                next(reversed(base.split(os.path.sep))) or "Unnamed corpus"
            )

    checker = Checker(template_data, quote=quote, delimiter=delimiter, escape=escape)
    text_attrs: list[tuple[str, str]] = [
        (lay, attr)
        for lay, props in template_data["layer"].items()
        for attr in {
            aname
            for aname, ameta in props.get("attributes", {}).items()
            if ameta.get("type") == "text"
        }
    ]
    no_index: set[tuple[str, str]] | list[list[str]] = set()
    no_index_callback: Callable = lambda c, h, f, *_: cast(
        set[tuple[str, str]], no_index
    ).add(
        next(
            (
                (lay, attr)
                for lay, attr in text_attrs
                if f.startswith(f"{lay}_{attr}.".lower())
                and len(c[h.index(attr)]) > 2000
            ),
            ("", ""),
        )
    )
    if is_zip:
        print(
            "Warning: not running checks on archives. Un-archive the corpus if you want to run checks."
        )
        print(
            "Some optimization procedures only apply when checking the corpus; skipping the checks might produced a sub-optimized corpus."
        )
    elif skip_check:
        print("Warning: not running checks on the corpus.")
        print(
            "Some optimization procedures only apply when checking the corpus; skipping the checks might produced a sub-optimized corpus."
        )
    else:
        tok = template_data["firstClass"]["token"]
        n_tokens = {"n": 0}
        n_tokens_callback: Callable = lambda c, h, f, *_: n_tokens.__setitem__(
            "n", n_tokens["n"] + (1 if f.startswith(tok.lower() + ".") else 0)
        )
        callback: Callable = lambda c, h, f, *_: n_tokens_callback(
            c, h, f, *_
        ) or no_index_callback(c, h, f, *_)
        checker.run_checks(base, full=True, add_zero=False, callback=callback)
        n_batches = max(1, ceil(log2(n_tokens["n"] / 1e6)))
        no_index = [[lay, attr] for lay, attr in no_index if lay and attr]

    headers: dict[str, str | None] = {
        "Content-Type": None,
        "X-API-Key": api_key,
        "X-API-Secret": secret,
        "X-LCPCLI-Version": str(__version__),
    }

    if not template_data and template:
        print(f"Using template: {template}")
        with open(template, "r", encoding="utf-8") as fo:
            template_data = json.load(fo)
    # if delete_template:
    #    os.remove(template)
    jso = {"template": template_data}

    has_media = template_data and template_data.get("meta", {}).get("mediaSlots", {})

    if has_media:
        assert os.path.isdir(base), NotImplementedError(
            "Multimedia corpora must be in an unzipped folder"
        )
        media_path = os.path.join(base, "media")
        assert os.path.isdir(media_path), NotImplementedError(
            "The media files should be placed inside a 'media' subfolder"
        )
        doc_name = cast(dict, template_data)["firstClass"]["document"]
        doc_fn = get_file_from_base(doc_name, os.listdir(base))
        with open(os.path.join(base, doc_fn), "r", encoding="utf-8") as doc_file:
            media_ncol = -1
            doc_csv = csv.reader(
                doc_file,
                delimiter=delimiter or ",",
                quotechar=quote or '"',
                escapechar=escape or None,
            )
            for nline, cols in enumerate(doc_csv, start=1):
                if media_ncol < 0:
                    media_ncol = next(n for n, col in enumerate(cols) if col == "media")
                    continue
                media_obj = json.loads(cols[media_ncol])
                for media_name, media_attr in has_media.items():
                    if media_attr.get("isOptional"):
                        continue
                    media_filename = media_obj.get(media_name)
                    assert media_filename, ReferenceError(
                        f"No file referenced for '{media_name}' in document line {nline} ({cols})"
                    )
                    media_filepath = os.path.join(media_path, media_filename)
                    assert os.path.isfile(media_filepath), FileNotFoundError(
                        f"File '{media_filename}' not found in {media_path} for document line {nline} ({cols})"
                    )

    if check_only:
        if not skip_check:
            print("Checks over.")
        return

    default = "vian" if vian else "lcp"
    this_corpus_projects = [default]
    if project:
        this_corpus_projects.append(project)
    jso["projects"] = this_corpus_projects

    try_send: bool = True
    overwrite_id: int = 0
    while try_send:
        print("Sending template...")
        url = CREATE_URL if live else CREATE_URL_TEST
        if provided_url:
            url = provided_url
        url = url.removesuffix("/") + "/create"
        jso["n_batches"] = n_batches or 10
        jso["no_index"] = list(no_index)
        jso["overwrite"] = True if overwrite_id and overwrite_id > 0 else False
        resp = post(url, headers=headers, json=jso)  # type: ignore
        data = resp.json()
        jso["quote"] = quote
        jso["delimiter"] = delimiter
        jso["escape"] = escape
        ret = check_template_and_send(
            data, headers, jso, corpus, base, filt, live, provided_url=provided_url
        )
        if ret and ret[0] == "already exists":
            overwrite_id = int(ret[1])
            ret = tuple()
            corpus_name = (
                template_data.get("meta", {}).get("name", "") if template_data else ""
            )
            if force_corpus_overwrite:
                continue
            print(
                f"Do you want to overwrite the existing corpus {corpus_name} (#{overwrite_id}) with this one?"
            )
            should_overwrite = input("Type Y/YES/y/yes or N/NO/n/no: ")
            if not re.match(r"(y|yes)", should_overwrite, re.IGNORECASE):
                overwrite_id = 0
                print("Aborting the upload process.")
                return
        else:
            try_send = False

    if not ret:
        return
    new_corpus_id = monitor_db_insert(*ret)
    if not new_corpus_id or new_corpus_id == 0:
        print("Upload failed, aborting now.")
        return

    status, error = ("finished", "")
    if has_media:
        media_type = (
            "video"
            if "video" in (x.get("mediaType", "") for x in has_media.values())
            else "audio"
        )
        status, error = send_media(
            data,
            headers,
            jso,
            corpus,
            base,
            filt,
            live,
            provided_url=provided_url,
            media_type=media_type,
        )

    has_images = template_data and any(
        y.get("type", "") == "image"
        for x in template_data.get("layer", {}).values()
        for y in x.get("attributes", {}).values()
    )
    if has_images:
        status, error = send_media(
            data,
            headers,
            jso,
            corpus,
            base,
            filt,
            live,
            provided_url=provided_url,
            media_type="image",
        )

    if status != "finished":
        print(f"Upload failed: {error}")
    else:
        if overwrite_id and overwrite_id > 0:
            status, error_or_job_id = overwrite_corpus(
                int(overwrite_id),
                new_corpus_id,
                headers,
                live=live,
                provided_url=provided_url,
            )
            if status == "failed":
                print(
                    f"Failed to overwrite corpus #{overwrite_id} with new corpus #{new_corpus_id}:"
                )
                print(error_or_job_id)
                return
            check_overwrite_url = CREATE_URL if live else CREATE_URL_TEST
            if provided_url:
                check_overwrite_url = provided_url
            check_overwrite_url = (
                check_overwrite_url.removesuffix("/")
                + f"/corpora/{error_or_job_id}/overwrite"
            )
            if not monitor_overwrite(check_overwrite_url, headers):
                print(
                    f"Failed to overwrite corpus #{overwrite_id} with new corpus #{new_corpus_id}."
                )
                print(
                    f"Corpus #{new_corpus_id} was still successuflly uploaded; corpus #{overwrite_id} is now disabled."
                )
                print(
                    f"Please contact an admin if you need to restore corpus #{overwrite_id}"
                )
                return
        print("Corpus uploaded.")


def send_media(
    data: dict[str, Any],
    headers: dict[str, Any],
    jso: dict[str, Any],
    corpus: str,
    base: str,
    filt: str | None,
    live: bool,
    provided_url: str = "",
    media_type: str = "audio",
) -> tuple[str, str]:
    """
    Send media files
    """
    project = data.get("project")
    target = data.get("target")
    user_id = data.get("user_id")
    job = data.get("job")
    if not project or not target or not user_id or not job:
        print(f"Failed:")
        for k, v in data.items():
            print(f"{k}: {v}")
        return ("failed", "Missing project, target, user_id or job in payload")

    time.sleep(3)

    jso.pop("check", None)
    jso["project"] = project
    jso["user_id"] = user_id
    jso["job"] = data["job"]
    jso["media"] = True

    media_path = os.path.join(base, "media")
    assert os.path.isdir(media_path), FileNotFoundError(
        f"No 'media' subfolder found at '{media_path}'"
    )

    files = [os.path.join(media_path, p) for p in os.listdir(media_path)]
    if not filt:
        filt = ""
    extensions = IMAGE_EXTENSIONS if media_type == "image" else AUDIOVIDEO_EXTENSIONS
    files = [fp for fp in files if filt in fp and fp.lower().endswith(extensions)]

    print(f"Sending media ({media_type}) data...")

    url = CREATE_URL if live else CREATE_URL_TEST
    if provided_url:
        url = provided_url
    upload_url = url.removesuffix("/") + f"/upload"
    tus_client = CustomTusClient(upload_url)
    fn_md5 = hashlib.md5(
        "".join(sorted(os.path.basename(fn) for fn in files)).encode()
    ).hexdigest()
    try:
        for file_path in files:
            metadata = {
                "job_id": job,
                "filename": os.path.basename(file_path),
                "files_md5": str(fn_md5),
                "media": "True",
            }
            headers["Upload-Metadata"] = metadata
            uploader = tus_client.uploader(
                file_path, chunk_size=1000 * 1024, headers=headers
            )
            data = uploader.upload()
            print(f"✅ Uploaded {file_path} to: {uploader.url}")
    except Exception as e:
        return ("failed", str(e))

    time.sleep(0.5)

    return (data.get("x-status", "failed"), data.get("x-error", ""))


def overwrite_corpus(
    previous_corpus_id: int,
    new_corpus_id: int,
    headers: dict[str, Any],
    live: bool,
    provided_url: str = "",
) -> tuple[str, str]:
    """
    Put to /corpora/ID/overwrite to overwrite the corpus
    """
    print(f"Overwriting corpus #{previous_corpus_id} with corpus #{new_corpus_id}...")

    jso = {"overwrite": previous_corpus_id}

    url = CREATE_URL if live else CREATE_URL_TEST
    if provided_url:
        url = provided_url
    url = url.removesuffix("/") + f"/corpora/{new_corpus_id}/overwrite"
    resp = requests.put(url, json=jso, headers=headers)  # type: ignore

    time.sleep(2)

    data = resp.json()
    return (data.get("status", "failed"), data.get("job", data.get("error", "")))


def monitor_overwrite(url: str, headers: dict[str, Any]) -> bool:
    """
    Poll /corpora/JOB_ID/overwrite to check the status of a job
    """
    wait = 8
    bads = ("stopped", "canceled", "failed")

    while True:
        resp = requests.get(url, headers=headers)  # type: ignore
        data = resp.json()

        status = data.get("status")
        if status in bads:
            if status == "failed":
                print("Overwriting failed:")
                print(data.get("msg", "Unkown error."))
            else:
                print("Overwriting was interrupted.")
            return False
        elif status == "finished":
            return True
        time.sleep(wait)


def check_template_and_send(
    data: dict[str, Any],
    headers: dict[str, Any],
    jso: dict[str, Any],
    corpus: str,
    base: str,
    filt: str | None,
    live: bool,
    provided_url: str = "",
) -> tuple:
    """
    Poll /schema to check if schema is done, then send data
    """
    project = data.get("project")
    target = data.get("target")
    user_id = data.get("user_id")
    job = data.get("job")
    if not project or not target or not user_id or not job:
        if re.search(r"corpus named \S+ already exists", data.get("error", "")):
            return ("already exists", data.get("corpus_id", "-1"))
        print(f"Failed:")
        for k, v in data.items():
            print(f"{k}: {v}")
        return tuple()

    url = CREATE_URL if live else CREATE_URL_TEST
    if provided_url:
        url = provided_url

    time.sleep(7)

    print("Checking template validity...", project)

    fin_data = check_template(data, project, headers, url)

    project = fin_data.get("project")
    if not project:
        print(f"Failed:")
        for k, v in fin_data.items():
            print(f"{k}: {v}")
        return tuple()
    jso.pop("template")
    jso["project"] = project
    jso["user_id"] = user_id
    jso["job"] = data["job"]

    if os.path.isdir(corpus):

        files = [  # {
            os.path.join(
                base, p
            )  # os.path.splitext(p)[0]: open(os.path.join(base, p), "rb")
            for p in os.listdir(base)
            if os.path.isfile(os.path.join(base, p))
        ]  # }
        if filt:
            files = [  # {
                k  #: v
                for k in files  # , v in files.items()
                if filt in k and k.endswith(VALID_EXTENSIONS + COMPRESSED_EXTENSIONS)
            ]  # }
    else:
        # files = {os.path.splitext(corpus)[0]: open(corpus, "rb")}
        files = [corpus]

    print("Sending data...")

    upload_url = url.removesuffix("/") + f"/upload"
    tus_client = CustomTusClient(upload_url)
    fn_md5 = hashlib.md5(
        "".join(sorted(os.path.basename(fn) for fn in files)).encode()
    ).hexdigest()
    for file_path in files:
        metadata = {
            "job_id": job,
            "filename": os.path.basename(file_path),
            "files_md5": fn_md5,
        }
        headers["Upload-Metadata"] = metadata
        uploader = tus_client.uploader(
            file_path, chunk_size=1000 * 1024, headers=headers
        )
        data = uploader.upload()
        print(f"✅ Uploaded {file_path} to: {uploader.url}")
    # resp = post(upload_url, params=jso, headers=headers, files=files, verify=False)  # type: ignore

    time.sleep(0.5)

    print("Waiting for server checks...")

    # try:
    #     data = resp.json()
    # except Exception:
    #     print("Error", resp)

    if "x-target" not in data:
        print(f"Failed:")
        for k, v in data.items():
            print(f"{k}: {v}")
        print("No target. Aborting.")
        return tuple()
    new_url = url + data["x-target"]
    jso["check"] = True
    return new_url, headers, jso


def monitor_db_insert(
    new_url: str, headers: dict[str, Any], jso: dict[str, Any]
) -> int:
    """
    Poll /upload and check the status of a job
    """
    status = None
    wait = 8
    progbar: tqdm | None = None
    total: int | float | None = None
    bads: set[str] = {"finished", "failed"}
    unit: str = "byte"

    while True:
        resp = post(new_url, headers=headers, params=jso)  # type: ignore
        data = resp.json()

        if data.get("status") != status and data["status"] not in bads:
            for k, v in data.items():
                if k != "target" and progbar:
                    progbar.write(f"{k}: {v}")
        status = data["status"]
        if status in bads:
            if progbar and total and status == "finished":
                progbar.n = progbar.total
                progbar.set_description("Tidying up", refresh=False)
                progbar.refresh()
                progbar.close()
                print(f"Status: {status}")
            elif status == "failed":
                print(f"Status: {status}")
                print(f"Info: {data.get('info','')}")
                if progbar:
                    for k, v in data.items():
                        if k != "target" and progbar:
                            progbar.write(f"{k}: {v}")
            if status == "finished":
                return data.get("corpus_id", -1)
            else:
                return 0
        stat = "" if not status else status.lower()
        current, tot, text, unit = data.get("progress", "///").split("/", 3)
        if "started" in stat:
            stat = text
        if tot:
            tot = int(tot)
        if current:
            current = int(current)
        if not total and tot:
            total = tot
        if not progbar and total:
            progbar = tqdm(total=total, desc=stat, unit_scale=True, unit=unit, ncols=80)
        if progbar is not None and current and tot != total and unit == "task":
            progbar.n = progbar.total
            progbar.refresh()
            progbar.close()
            total = tot
            progbar = tqdm(
                total=total, desc=stat, unit_scale=False, unit=unit, ncols=80
            )
        elif progbar is not None and current and tot == total:
            progbar.n = current
            progbar.set_description(stat, refresh=False)
            progbar.refresh()

        time.sleep(wait)
    if progbar:
        progbar.close()


def check_template(
    data: dict[str, Any], project: str, headers: dict[str, Any], url: str = ""
) -> dict[str, Any]:
    """
    Poll /schema to find out how template job is going
    """

    status = None
    elapsed = 0
    between_iter = 0.1
    wait = 800
    position = 0
    size = 20
    direction = 1
    bad_keys = {"status", "target", "job", "progress"}

    while True:
        if not status or not (elapsed * 10 % wait):
            url = url.removesuffix("/") + data["target"]
            cparams = {"job": data["job"], "project": project}
            resp = post(url, params=cparams, headers=headers)  # type: ignore
            data = resp.json()
            if data.get("status") != status:
                print("")
                for k, v in data.items():
                    if k not in bad_keys and v:
                        print(f"{k}: {v}")
            status = data["status"]
            if status == "failed":
                return {}
            elif status == "finished":
                print("")
                return data

        stat = "" if not status else status.lower().replace("started", "running")
        print(
            "\r[{}={}]: {}".format(" " * position, " " * (size - position), stat),
            end="",
        )
        sys.stdout.flush()

        position += 1 * direction
        if direction > 0 and position > size - 1:
            position = size
            direction = -1
        elif position < 1:
            position = 0
            direction = 1

        time.sleep(between_iter)
        elapsed += int(between_iter * 10)


def run() -> None:
    kwargs = _parse_cmd_line()
    lcp_upload(**kwargs)


if __name__ == "__main__":
    run()
