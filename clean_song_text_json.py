"""
clean_song_dividers.py

Scans one or more JSON files containing a "song_list" array and removes
stray asterisk-only divider lines from the "song_text" field.

KEEPS:   asterisk lines that immediately precede or follow a section header:
         Sanskrit | Tamil | English | End Of Song
REMOVES: any other line consisting solely of asterisks (used as visual dividers)

Usage:
    # Clean a single file (overwrites in place):
    python clean_song_dividers.py thyagarajar.json

    # Clean multiple files:
    python clean_song_dividers.py file1.json file2.json file3.json

    # Clean all JSON files in the current directory:
    python clean_song_dividers.py *.json

    # Dry-run (print changes without saving):
    python clean_song_dividers.py --dry-run thyagarajar.json
"""

import json
import re
import sys
import argparse
from pathlib import Path

# Section headers that legitimate asterisk wrappers surround
SECTION_HEADERS = {"Sanskrit", "Tamil", "English", "End Of Song"}

# Matches a line that is ONLY asterisks (after stripping <br /> and whitespace)
ASTERISK_ONLY = re.compile(r'^\*+$')

# Splits on <br /> keeping the delimiter so we can reassemble
SPLIT_ON_BR = re.compile(r'(<br\s*/?>)')


def split_lines(text: str) -> list[str]:
    """Split song_text into logical lines, preserving <br /> tokens."""
    # Each "line" in the HTML is terminated by <br />
    # We treat the text between <br /> markers as a line.
    parts = SPLIT_ON_BR.split(text)
    # parts alternates: content, <br />, content, <br />, ...
    return parts


def line_content(raw: str) -> str:
    """Strip whitespace and \r\n from a raw segment to get its display content."""
    return raw.strip().rstrip('\r\n').strip()


def is_asterisk_line(content: str) -> bool:
    return bool(ASTERISK_ONLY.match(content))


def is_section_header(content: str) -> bool:
    return content in SECTION_HEADERS


def clean_song_text(song_text: str) -> tuple[str, int]:
    """
    Remove stray asterisk divider lines from song_text HTML.
    Returns (cleaned_text, num_removed).
    """
    # Split into segments; odd-indexed segments are <br /> tokens
    parts = SPLIT_ON_BR.split(song_text)

    # Reconstruct logical lines as (index_of_content_part, display_content)
    # Content parts are at even indices; <br /> tokens at odd indices.
    # A "line" in the song is a content part + the <br /> that follows it (if any).

    # Build list of (part_index, display_content) for content parts only
    content_indices = list(range(0, len(parts), 2))  # 0, 2, 4, ...

    contents = [line_content(parts[i]) for i in content_indices]

    # Identify which content parts to REMOVE.
    # A content part is a stray divider if:
    #   - Its display content is asterisk-only, AND
    #   - Neither the previous nor the next content part is a section header.
    to_remove = set()

    for pos, idx in enumerate(content_indices):
        c = contents[pos]
        if not is_asterisk_line(c):
            continue

        prev_content = contents[pos - 1] if pos > 0 else ""
        next_content = contents[pos + 1] if pos + 1 < len(contents) else ""

        if is_section_header(prev_content) or is_section_header(next_content):
            # This asterisk line is a legitimate section wrapper — keep it
            continue

        # Stray divider — mark for removal
        to_remove.add(idx)

    if not to_remove:
        return song_text, 0

    # Rebuild parts, skipping removed content parts and their trailing <br />
    new_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 0:  # content part
            if i in to_remove:
                # Also skip the immediately following <br /> token (i+1)
                # by not appending either — handled below
                continue
            else:
                new_parts.append(part)
        else:  # <br /> token
            # Skip if the preceding content part was removed
            preceding_content_idx = i - 1
            if preceding_content_idx in to_remove:
                continue
            new_parts.append(part)

    return "".join(new_parts), len(to_remove)


def process_file(path: Path, dry_run: bool) -> dict:
    """Process a single JSON file. Returns a summary dict."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    song_list = data.get("song_list", [])
    total_removed = 0
    songs_changed = 0

    for song in song_list:
        original = song.get("song_text", "")
        cleaned, removed = clean_song_text(original)
        if removed:
            song["song_text"] = cleaned
            total_removed += removed
            songs_changed += 1

    if not dry_run and total_removed > 0:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "file": str(path),
        "songs_changed": songs_changed,
        "dividers_removed": total_removed,
    }


def main():
    parser = argparse.ArgumentParser(description="Remove stray asterisk dividers from song_text JSON fields.")
    parser.add_argument("files", nargs="+", help="JSON file(s) to process")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without saving")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — no files will be modified.\n")

    grand_total = 0
    for pattern in args.files:
        for filepath in sorted(Path(".").glob(pattern) if "*" in pattern else [Path(pattern)]):
            if not filepath.exists():
                print(f"  WARNING: {filepath} not found — skipping.")
                continue
            result = process_file(filepath, dry_run=args.dry_run)
            status = "would update" if args.dry_run else "updated"
            if result["dividers_removed"]:
                print(f"  {result['file']}: {status} {result['songs_changed']} song(s), "
                      f"removed {result['dividers_removed']} stray divider(s).")
            else:
                print(f"  {result['file']}: nothing to clean.")
            grand_total += result["dividers_removed"]

    print(f"\nDone. Total stray dividers {'found' if args.dry_run else 'removed'}: {grand_total}")


if __name__ == "__main__":
    main()