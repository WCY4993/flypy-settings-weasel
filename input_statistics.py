"""Read existing learning counts and optional text-free timing metadata off the input path."""
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def learning_row(line):
    fields = line.rstrip('\r\n').split('\t')
    if len(fields) != 5:
        return None
    mode, code, text, count, manual = fields
    if (mode not in ('t', 's') or not code.isascii() or not code.isalpha()
            or not code.islower() or not count.isdecimal() or len(count) > 18
            or not manual.isdecimal() or not text):
        return None
    return (mode, code, text), int(count)


def read_snapshot(root):
    latest, days = {}, defaultdict(lambda: dict(commits=0, characters=0, manual=0, new=0))
    timed = 0
    first_time = None
    run_seconds = run_chars = run_commits = 0
    speed_seconds = speed_chars = 0
    previous_time = None

    def finish_run():
        nonlocal speed_seconds, speed_chars, run_seconds, run_chars, run_commits
        # Second-resolution timing needs a useful sample, not one rapid selection.
        if run_seconds >= 10 and run_commits >= 5:
            speed_seconds += run_seconds
            speed_chars += run_chars
        run_seconds = run_chars = run_commits = 0

    path = Path(root) / 'flypy_learning.tsv'
    pending = None
    if path.is_file():
        with path.open(encoding='utf-8', errors='replace') as stream:
            for line in stream:
                if not line.endswith('\n'):
                    continue  # Ignore a concurrent, incomplete final append.
                row = learning_row(line)
                if row:
                    latest[row[0]] = row[1]
                    pending = row
                    continue
                fields = line.rstrip('\r\n').split('\t')
                if len(fields) != 6 or fields[0] != '#stats-v1' or pending is None:
                    pending = None
                    continue
                try:
                    timestamp, chars, manual, fresh, gap = map(int, fields[1:])
                    valid = (946684800 <= timestamp <= 4102444800 and chars == len(pending[0][2])
                             and 1 <= chars <= 128 and manual in (0, 1) and fresh in (0, 1)
                             and -1 <= gap <= 30)
                    day = datetime.fromtimestamp(timestamp).date().isoformat() if valid else None
                except (ValueError, OverflowError, OSError):
                    day = None
                pending = None
                if day is None:
                    continue
                daily = days[day]
                daily['commits'] += 1
                daily['characters'] += chars
                daily['manual'] += manual
                daily['new'] += fresh
                timed += 1
                first_time = timestamp if first_time is None else min(first_time, timestamp)
                if previous_time is None or gap < 0 or timestamp - previous_time != gap:
                    finish_run()
                else:
                    run_seconds += gap
                    run_chars += chars
                    run_commits += 1
                previous_time = timestamp
    finish_run()
    words, characters = Counter(), Counter()
    for (_mode, _code, text), count in latest.items():
        words[text] += count
        for char in text:
            characters[char] += count
    total = sum(words.values())
    count_chars = sum(len(text) * count for text, count in words.items())
    longest = max(words, key=lambda text: (len(text), words[text], text), default='')
    return dict(words=words, characters=characters, selections=total, total_characters=count_chars,
                unique_words=len(words), average_length=count_chars / total if total else 0,
                longest=longest, days=dict(sorted(days.items(), reverse=True)), timed_records=timed,
                first_time=first_time, speed_seconds=speed_seconds,
                speed_cpm=60 * speed_chars / speed_seconds if speed_seconds else None)


def ranking(snapshot, kind, limit=100):
    rows = snapshot['characters'] if kind == '常用字（含詞內用字）' else snapshot['words']
    items = ((text, count) for text, count in rows.items()
             if kind != '常用詞（兩字以上）' or len(text) >= 2)
    return sorted(items, key=lambda row: (-row[1], row[0]))[:limit]
