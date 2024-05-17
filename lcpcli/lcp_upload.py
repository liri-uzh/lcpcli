#! /usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import time

from typing import Any, cast

import requests

from tqdm import tqdm

from .cli import _parse_cmd_line

CREATE_URL = "https://lcp.test.linguistik.uzh.ch/create"
UPLOAD_URL = "https://lcp.test.linguistik.uzh.ch/upload"
CREATE_URL_TEST = "http://localhost:9090/create"
UPLOAD_URL_TEST = "http://localhost:9090/upload"

VALID_EXTENSIONS = ("csv",)
COMPRESSED_EXTENSIONS = ("zip", "tar", "tar.gz", "tar.xz", "7z")
MEDIA_EXTENSIONS = ("mp3", "mp4", "wav", "ogg")


def lcp_upload(
    corpus: str = "",
    api_key: str = "",
    template: str | None = "",
    secret: str = "",
    project: str | None = None,
    vian: bool = False,
    live: bool = False,
    to: str = "",
    check_only: bool = False,
    **kwargs,
) -> None:

    filt = None
    # delete_template = False
    template_data = None

    if os.path.isfile(corpus):
        if not corpus.endswith(COMPRESSED_EXTENSIONS):
            ext = ", ".join(COMPRESSED_EXTENSIONS)
            print(
                f"If corpus is a file, it must have one of the following extensions: {ext}"
            )
            return
        base = os.path.dirname(corpus)
        filt = os.path.basename(base)
    else:
        total_size = sum(
            [
                os.path.getsize(os.path.join(corpus, f))
                for f in os.listdir(corpus)
                if f.endswith(".csv")
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
        from tarfile import TarFile, is_tarfile
        from zipfile import ZipFile, is_zipfile
        from py7zr import SevenZipFile, is_7zfile

        ziptar = [
            (".zip", is_zipfile, ZipFile, "namelist"),
            (".tar", is_tarfile, TarFile, "getnames"),
            (".tar.gz", is_tarfile, TarFile, "getnames"),
            (".tar.xz", is_tarfile, TarFile, "getnames"),
            (".7z", is_7zfile, SevenZipFile, "getnames"),
        ]
        found = False
        for ext, check, opener, method in ziptar:
            if not corpus.endswith(ext):
                continue
            if not check(corpus):
                print(f"Problem with archive: {corpus}")
                return
            with opener(corpus, "r") as compressed:
                for f in getattr(compressed, method)():
                    if not f.endswith(".json"):
                        continue
                    found = True
                    print(f"Using {f} from archive as template file...")
                    dest = "."
                    if ext != ".7z":
                        compressed.extract(f, dest)
                    else:
                        compressed.extract(dest, [f])
                    template = f
                    # delete_template = True
            if not found:
                print(f"Error: no JSON files found in archive: {corpus}")
                return
    elif not template and os.path.isdir(corpus):
        template = next((i for i in os.listdir(corpus) if i.endswith(".json")), None)
        if template is None:
            print("Error: no template specified and no JSON found in corpus directory.")
            return
        template = os.path.join(corpus, template)

    headers: dict[str, str | None] = {
        "Content-Type": None,
        "X-API-Key": api_key,
        "X-API-Secret": secret,
    }

    if not template_data and template:
        print(f"Using template: {template}")
        with open(template, "r") as fo:
            template_data = json.load(fo)
    # if delete_template:
    #    os.remove(template)
    jso = {"template": template_data}

    has_media = template_data and template_data.get("meta", {}).get("mediaSlots", {})

    if has_media:
        assert os.path.isdir(corpus), NotImplementedError(
            "Multimedia corpora must be in an unzipped folder"
        )
        media_path = os.path.join(corpus, "media")
        assert os.path.isdir(media_path), NotImplementedError(
            "The media files should be placed inside a 'media' subfolder"
        )
        doc_name = cast(dict, template_data)["firstClass"]["document"]
        with open(os.path.join(corpus, f"{doc_name.lower()}.csv"), "r") as doc_file:
            media_ncol = -1
            nline = 0
            while True:
                line = doc_file.readline()
                nline += 1
                if not line:
                    break
                cols = line.rstrip().split("\t")
                if media_ncol < 0:
                    media_ncol = next(n for n, col in enumerate(cols) if col == "media")
                    continue
                media_obj = json.loads(cols[media_ncol])
                for media_name, media_attr in has_media.items():
                    if media_attr.get("isOptional"):
                        continue
                    media_filename = media_obj.get(media_name)
                    assert media_filename, ReferenceError(
                        f"No file referenced for '{media_name}' in document line {nline} ({line})"
                    )
                    media_filepath = os.path.join(media_path, media_filename)
                    assert os.path.isfile(media_filepath), FileNotFoundError(
                        f"File '{media_filename}' not found in {media_path} for document line {nline} ({line})"
                    )

    if check_only:
        print("Checks over.")
        return

    default = "vian" if vian else "lcp"
    this_corpus_projects = [default]
    if project:
        this_corpus_projects.append(project)
    jso["projects"] = this_corpus_projects

    print("Sending template...")
    url = CREATE_URL if live else CREATE_URL_TEST
    if to:
        url = f"{to}/create"
    resp = requests.post(url, headers=headers, json=jso)  # type: ignore
    data = resp.json()
    ret = check_template_and_send(data, headers, jso, corpus, base, filt, live, to=to)
    if not ret:
        return
    if not monitor_upload(*ret):
        return

    status, error = ("finished", "")
    if has_media:
        status, error = send_media(data, headers, jso, corpus, base, filt, live, to=to)

    if status != "finished":
        print(f"Media upload failed: {error}")
    else:
        print("Corpus uploaded.")


def send_media(
    data: dict[str, Any],
    headers: dict[str, Any],
    jso: dict[str, Any],
    corpus: str,
    base: str,
    filt: str | None,
    live: bool,
    to: str = "",
) -> tuple[str, str]:
    """
    Poll /schema to check if schema is done, then send data
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

    files = {
        os.path.splitext(p)[0]: open(os.path.join(media_path, p), "rb")
        for p in os.listdir(media_path)
    }
    if filt:
        files = {
            k: v for k, v in files.items() if filt in k and k.endswith(MEDIA_EXTENSIONS)
        }

    print("Sending media data...")

    url = UPLOAD_URL if live else UPLOAD_URL_TEST
    if to:
        url = f"{to}/upload"
    resp = requests.post(url, params=jso, headers=headers, files=files)  # type: ignore

    time.sleep(2)

    data = resp.json()
    return (data.get("status", "failed"), data.get("error", ""))


def check_template_and_send(
    data: dict[str, Any],
    headers: dict[str, Any],
    jso: dict[str, Any],
    corpus: str,
    base: str,
    filt: str | None,
    live: bool,
    to: str = "",
) -> tuple:
    """
    Poll /schema to check if schema is done, then send data
    """
    project = data.get("project")
    target = data.get("target")
    user_id = data.get("user_id")
    job = data.get("job")
    if not project or not target or not user_id or not job:
        print(f"Failed:")
        for k, v in data.items():
            print(f"{k}: {v}")
        return tuple()

    time.sleep(7)

    print("Checking template validity...")

    fin_data = check_template(data, project, headers)

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

        files = {
            os.path.splitext(p)[0]: open(os.path.join(base, p), "rb")
            for p in os.listdir(base)
            if os.path.isfile(os.path.join(base, p))
        }
        if filt:
            files = {
                k: v
                for k, v in files.items()
                if filt in k and k.endswith(VALID_EXTENSIONS + COMPRESSED_EXTENSIONS)
            }
    else:
        files = {os.path.splitext(corpus)[0]: open(corpus, "rb")}

    print("Sending data...")

    url = UPLOAD_URL if live else UPLOAD_URL_TEST
    if to:
        url = f"{to}/upload"
    resp = requests.post(url, params=jso, headers=headers, files=files)  # type: ignore
    print("files", files)

    time.sleep(5)

    print("Checking corpus validity...")

    data = resp.json()
    print("data", data)
    if "target" not in data:
        print(f"Failed:")
        for k, v in data.items():
            print(f"{k}: {v}")
        print("No target. Aborting.")
        return tuple()
    new_url = data["target"]
    jso["check"] = True
    return new_url, headers, jso


def monitor_upload(new_url: str, headers: dict[str, Any], jso: dict[str, Any]) -> bool:
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
        resp = requests.post(new_url, headers=headers, params=jso)  # type: ignore
        data = resp.json()

        print("monitoring", data)

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
            return status == "finished"
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
    data: dict[str, Any], project: str, headers: dict[str, Any]
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
            url = data["target"]
            cparams = {"job": data["job"], "project": project}
            resp = requests.post(url, params=cparams, headers=headers)  # type: ignore
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
