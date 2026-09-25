#!/usr/bin/env python3
"""Download this dataset's release assets, verify them, and lay them out for the runner.

GitHub release asset names cannot contain `/`, so the ten assets are flat
(`temporal-public-train.csv`, ...) and this script restores the layout the benchmark expects:

    <dest>/<level>/public/train.csv
    <dest>/<level>/public/eval.csv
    <dest>/<level>/private/holdout.csv
    <dest>/<level>/meta.json
    <dest>/<level>/quality.json

for each level in temporal, station_disjoint. Every file is checked against the release's own
recorded size and against `SHA256SUMS`, so a download that does not match is refused rather than
silently used.

The repository is private, so a credential is needed: either the `gh` CLI (already authenticated) or
`GITHUB_TOKEN` in the environment.

    python3 get_dataset.py --dest ./task
    python3 get_dataset.py --dest ./task --level temporal

The equivalent by hand:

    gh release download v2026.09 --repo earino/noaa-tide-flooding --dir ./flat
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

REPO = "earino/noaa-tide-flooding"
LEVELS = ("temporal", "station_disjoint")
# asset name -> destination inside the dataset directory
LAYOUT = {}
for _level in LEVELS:
    for _asset, _relative in (
        ("public/train.csv", "public/train.csv"),
        ("public/eval.csv", "public/eval.csv"),
        ("private/holdout.csv", "private/holdout.csv"),
        ("meta.json", "meta.json"),
        ("quality.json", "quality.json"),
    ):
        LAYOUT[f"{_level}-{_asset.replace('/', '-')}"] = f"{_level}/{_relative}"


def token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def auth_headers() -> dict:
    value = token()
    return {"Authorization": "Bearer " + value} if value else {}


def release(tag: str) -> dict:
    """Read the release through `gh` when available, else the API."""
    if shutil.which("gh") and not token():
        done = subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/{tag}"],
                              capture_output=True, text=True)
        if done.returncode == 0:
            return json.loads(done.stdout)
        raise SystemExit(f"gh could not read {REPO}@{tag}: {done.stderr.strip()[:200]}")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
        headers={"Accept": "application/vnd.github+json", **auth_headers()})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except Exception as exc:
        raise SystemExit(f"could not read {REPO}@{tag}: {type(exc).__name__}. "
                         "The repository is private; authenticate with `gh auth login` or set "
                         "GITHUB_TOKEN.") from None


def download(asset: dict, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("gh") and not token():
        done = subprocess.run(["gh", "release", "download", asset["_tag"], "--repo", REPO,
                               "--pattern", asset["name"], "--dir", str(dest.parent),
                               "--clobber"], capture_output=True, text=True)
        if done.returncode:
            raise SystemExit(f"gh download failed: {done.stderr.strip()[:200]}")
        (dest.parent / asset["name"]).replace(dest)
        return dest
    request = urllib.request.Request(
        asset["url"], headers={"Accept": "application/octet-stream", **auth_headers()})
    with urllib.request.urlopen(request, timeout=600) as response, dest.open("wb") as stream:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            stream.write(chunk)
    return dest


def sha256_of(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", default="task", help="where to write the dataset directory")
    parser.add_argument("--tag", default="v2026.09")
    parser.add_argument("--level", default=None, choices=list(LEVELS),
                        help="fetch one level instead of both")
    parser.add_argument("--sums", default=None,
                        help="path to SHA256SUMS (default: ./SHA256SUMS if present)")
    args = parser.parse_args()

    info = release(args.tag)
    assets = {a["name"]: a for a in info["assets"]}
    wanted = {name: relative for name, relative in LAYOUT.items()
              if args.level is None or relative.startswith(args.level + "/")}
    missing = [name for name in wanted if name not in assets]
    if missing:
        raise SystemExit(f"release {args.tag} is missing assets: {missing}")

    dest_root = Path(args.dest)
    written = []
    for name, relative in wanted.items():
        asset = dict(assets[name], _tag=args.tag)
        path = dest_root / relative
        download(asset, path)
        size = path.stat().st_size
        if asset["size"] != size:
            raise SystemExit(f"{name}: downloaded {size} bytes, release records {asset['size']}")
        written.append((relative, size, sha256_of(path)))
        print(f"  {name:32} -> {relative:36} {size:>12,} B")

    sums = Path(args.sums) if args.sums else Path("SHA256SUMS")
    if sums.is_file():
        expected = {}
        for line in sums.read_text().splitlines():
            digest, _, path = line.partition("  ")
            expected[path.strip()] = digest
        problems = [relative for relative, _, digest in written
                    if relative in expected and expected[relative] != digest]
        if problems:
            raise SystemExit(f"SHA256SUMS disagrees for: {problems}")
        print(f"  verified against {sums}")
    else:
        print("  note: no SHA256SUMS next to this script, sizes printed above for comparison")

    print(f"\nwrote {dest_root}/ (runner layout): <level>/public/, <level>/private/, meta.json, quality.json")
    print("next: python3 code/qualify_dataset.py " + str(dest_root / (args.level or "temporal")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
