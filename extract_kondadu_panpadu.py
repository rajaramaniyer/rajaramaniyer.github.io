#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

DEFAULT_EXCLUDED_ATTRIBUTES = {
    "id",
    "ID",
    "theme",
    "artist",
    "raga",
    "talam",
    "album",
    "song_type",
    "song_number",
    "created_date",
    "artist_type",
}


def find_case_insensitive_key(mapping, key):
    for candidate in mapping.keys():
        if candidate.lower() == key.lower():
            return candidate
    return None


def remove_keys(item, excluded):
    excluded_lower = {key.lower() for key in excluded}
    return {
        k: v
        for k, v in item.items()
        if k.lower() not in excluded_lower
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract matching entries from a JSON file into a new JSON file. "
            "You can use --attribute/--value, the shortcut --artistname, and "
            "customize output fields."
        )
    )
    parser.add_argument(
        "--input",
        default="/Users/rajaramaniyer/Downloads/kondadu-panpadu.json",
        help="Path to the source JSON file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to save the extracted JSON output.",
    )
    parser.add_argument(
        "--attribute",
        "--field",
        dest="attribute",
        help="Attribute/key to match on (for example: Artistname, title, id).",
    )
    parser.add_argument(
        "--value",
        dest="value",
        help="Exact value to match for the selected attribute.",
    )
    parser.add_argument(
        "--artistname",
        dest="artistname_value",
        help="Shortcut for matching the Artistname field.",
    )
    parser.add_argument(
        "--contains",
        action="store_true",
        help="Match if the value contains the given text (case-insensitive) instead of exact match.",
    )
    parser.add_argument(
        "--exclude-attribute",
        action="append",
        dest="exclude_attributes",
        default=None,
        help=(
            "Extra attribute to remove from output. May be supplied multiple times. "
            "Defaults to removing known metadata fields."
        ),
    )
    parser.add_argument(
        "--album-value",
        dest="album_value",
        default=None,
        help="Set a new album value for every extracted record.",
    )
    parser.add_argument(
        "--id-prefix",
        dest="id_prefix",
        default=None,
        help="Prefix for newly generated ids (for example: BR).",
    )
    args = parser.parse_args()

    if args.artistname_value is not None:
        args.attribute = args.attribute or "Artistname"
        args.value = args.artistname_value

    if not args.attribute or not args.value:
        parser.error(
            "Provide --attribute and --value, or use --artistname <value>."
        )

    excluded_attributes = list(DEFAULT_EXCLUDED_ATTRIBUTES)
    if args.exclude_attributes:
        excluded_attributes.extend(args.exclude_attributes)

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if (
        not isinstance(data, dict)
        or "song_list" not in data
        or not isinstance(data["song_list"], list)
    ):
        raise SystemExit(
            "The input JSON must be a JSON object with a top-level 'song_list' list."
        )

    matches = []
    for item in data["song_list"]:
        if not isinstance(item, dict):
            continue

        actual_key = find_case_insensitive_key(item, args.attribute)
        if actual_key is None:
            continue

        field_value = item[actual_key]
        if field_value is None:
            continue

        text = str(field_value)
        target = args.value

        if args.contains:
            matched = target.lower() in text.lower()
        else:
            matched = text == target

        if matched:
            matches.append(item)

    cleaned_matches = []
    for index, item in enumerate(matches, start=1):
        cleaned = remove_keys(item, excluded_attributes)

        if args.album_value is not None:
            cleaned["album"] = args.album_value

        if args.id_prefix is not None:
            cleaned["id"] = f"{args.id_prefix}{index}"

        cleaned_matches.append(cleaned)

    result = {"song_list": cleaned_matches}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        f"Extracted {len(cleaned_matches)} matching entries to {output_path}"
    )


if __name__ == "__main__":
    main()
