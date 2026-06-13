#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import sys

TRAILING_COMMA_PATTERN = re.compile(r',\s*(?=[}\]])')


def load_json(path: pathlib.Path):
    raw = path.read_text(encoding='utf-8')
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = TRAILING_COMMA_PATTERN.sub('', raw)
        return json.loads(cleaned)


def read_file_content(source_dir: pathlib.Path, filename: str) -> str:
    if not filename:
        return ''
    file_path = source_dir / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Missing source file: {file_path}")
    return file_path.read_text(encoding='utf-8').strip()


def htmlify(text: str) -> str:
    if not text:
        return ''
    lines = text.splitlines()
    return '<br />'.join(line.rstrip() for line in lines)


def build_song_text(entry: dict, source_dir: pathlib.Path) -> str:
    parts = []
    if entry.get('sanskritFileName'):
        sanskrit_text = read_file_content(source_dir, entry['sanskritFileName'])
        if sanskrit_text:
            parts.append('**********<br />Sanskrit<br />**********<br />' + htmlify(sanskrit_text))
    if entry.get('tamilFileName'):
        tamil_text = read_file_content(source_dir, entry['tamilFileName'])
        if tamil_text:
            parts.append('**********<br />Tamil<br />**********<br />' + htmlify(tamil_text))
    if not parts:
        raise ValueError(f"No Tamil or Sanskrit source file configured for entry id={entry.get('id')}")
    return '<br /><br />'.join(parts) + '<br /><br />*****************<br />End of Song<br />*****************'


def write_json(path: pathlib.Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Update premikagurusthuthi.json entries with song_text from source text files.'
    )
    parser.add_argument(
        '--json', '-j',
        default='encrypted/premikagurusthuthi.json',
        help='Path to the premikagurusthuthi JSON file.',
    )
    parser.add_argument(
        '--source-dir', '-s',
        default='~/books/srisrianna/premikendra-sadguru-stuti',
        help='Directory containing the Tamil and Sanskrit source text files.',
    )
    parser.add_argument(
        '--backup', '-b',
        action='store_true',
        help='Create a .bak backup of the JSON file before writing changes.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Compute updates without writing the JSON file.',
    )
    args = parser.parse_args()

    json_path = pathlib.Path(args.json).expanduser().resolve()
    source_dir = pathlib.Path(args.source_dir).expanduser().resolve()

    if not json_path.exists():
        print(f'ERROR: JSON file not found: {json_path}', file=sys.stderr)
        return 1
    if not source_dir.exists():
        print(f'ERROR: Source directory not found: {source_dir}', file=sys.stderr)
        return 1

    data = load_json(json_path)
    if not isinstance(data, dict) or 'song_list' not in data:
        print('ERROR: JSON file does not contain a top-level song_list array.', file=sys.stderr)
        return 1

    updated = 0
    missing = 0
    for entry in data['song_list']:
        try:
            new_text = build_song_text(entry, source_dir)
        except FileNotFoundError as exc:
            print(f'WARNING: {exc}', file=sys.stderr)
            missing += 1
            continue
        except ValueError as exc:
            print(f'WARNING: {exc}', file=sys.stderr)
            missing += 1
            continue

        old_text = entry.get('song_text', '')
        if old_text != new_text:
            entry['song_text'] = new_text
            updated += 1

    print(f'Processed {len(data["song_list"])} entries.')
    print(f'Updated song_text on {updated} entries.')
    if missing:
        print(f'Skipped {missing} entries because of missing source files or metadata.', file=sys.stderr)

    if not args.dry_run:
        if args.backup:
            backup_path = json_path.with_suffix(json_path.suffix + '.bak')
            backup_path.write_text(json_path.read_text(encoding='utf-8'), encoding='utf-8')
            print(f'Created backup: {backup_path}')
        write_json(json_path, data)
        print(f'Wrote updated JSON to {json_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
