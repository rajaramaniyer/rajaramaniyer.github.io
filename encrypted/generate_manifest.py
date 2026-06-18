#!/usr/bin/env python3
"""
generate_manifest.py

Scans a local library.json for every book "url", hashes the corresponding
local file's actual bytes (SHA-256), and writes manifest.json mapping each
URL to its current content hash.

This manifest is what the Flutter app compares against to decide whether a
book's content has genuinely changed - instead of relying on the server's
Last-Modified/ETag headers, which on GitHub Pages reflect the last deploy
time of the whole site, not whether a specific file's content changed.

Usage (with no arguments, assuming this script lives inside the "encrypted"
folder alongside library.json, and that folder is a direct subfolder of the
repo root that GitHub Pages serves from):
    python generate_manifest.py

All defaults are derived from where this script physically sits:
  - library.json is expected next to this script
  - manifest.json is written next to this script
  - repo root defaults to the parent of this script's folder (since this
    script lives in repo_root/encrypted/, one level up from it is repo_root)
  - base URL defaults to https://rajaramaniyer.github.io

Every default can still be overridden, e.g.:
    python generate_manifest.py --repo-root /path/to/other/repo

Run this after editing any book JSON file, before pushing. It assumes the
repo root maps 1:1 onto the site's URL paths, which is standard for GitHub
Pages (e.g. repo_root/encrypted/rangashathakam.json is served at
https://rajaramaniyer.github.io/encrypted/rangashathakam.json).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://rajaramaniyer.github.io"
DEFAULT_LIBRARY = SCRIPT_DIR / "library.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "manifest.json"
DEFAULT_REPO_ROOT = SCRIPT_DIR.parent  # one level up from "encrypted/"


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_urls(data) -> set:
    """Recursively pull every string value of a 'url' key out of library.json,
    regardless of how deeply nested the book entries are."""
    urls = set()

    def _walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "url" and isinstance(value, str):
                    urls.add(value)
                else:
                    _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    return urls


def url_to_local_path(url: str, base_url: str, repo_root: Path) -> Path:
    base_host = urlparse(base_url).netloc
    parsed = urlparse(url)

    if parsed.netloc != base_host:
        raise ValueError(
            f"host '{parsed.netloc}' does not match base host '{base_host}'"
        )

    relative = parsed.path.lstrip("/")
    return repo_root / relative


def main():
    parser = argparse.ArgumentParser(
        description="Generate manifest.json of content hashes for books in library.json"
    )
    parser.add_argument(
        "--library",
        default=str(DEFAULT_LIBRARY),
        help=f"Path to local library.json (default: {DEFAULT_LIBRARY})",
    )
    parser.add_argument(
        "--repo-root",
        default=str(DEFAULT_REPO_ROOT),
        help=(
            "Local repo root that GitHub Pages serves from, i.e. the folder "
            f"whose contents map onto the base URL (default: {DEFAULT_REPO_ROOT})"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the site (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Where to write manifest.json (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    with open(args.library, "r", encoding="utf-8") as f:
        library_data = json.load(f)

    urls = extract_urls(library_data)
    if not urls:
        print("No 'url' fields found in library.json - check its structure.", file=sys.stderr)
        sys.exit(1)

    manifest = {}
    missing = []

    for url in sorted(urls):
        try:
            local_path = url_to_local_path(url, args.base_url, repo_root)
        except ValueError as e:
            print(f"Skipping {url}: {e}", file=sys.stderr)
            continue

        if not local_path.is_file():
            missing.append((url, local_path))
            continue

        digest = sha256_of_file(local_path)
        manifest[url] = digest
        print(f"Hashed {url} -> {digest[:12]}...")

    if missing:
        print("\nWARNING: could not find local files for these URLs:", file=sys.stderr)
        for url, path in missing:
            print(f"  {url} (expected at {path})", file=sys.stderr)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    print(f"\nWrote manifest with {len(manifest)} entries to {output_path}")

    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
