"""Fingerprints of the raw data files (R5, from the real-time data archives).

What this file does
    Stores a SHA-256 fingerprint of every raw data file in nni_model/data/,
    and checks that each file still has the fingerprint it had when it was
    downloaded. A fingerprint is a 64-character code calculated from every
    byte of a file: change one byte and the code changes.

Why it matters
    A data snapshot is evidence: the figures in the book and the app come
    from these files. The contracts check that values are complete and in
    range; the fingerprint checks that the file is the one downloaded, with
    nothing edited by hand since. ALFRED and the UK real-time database keep
    each vintage unchanged in the same way.

Inputs
    The CSV files under nni_model/data/, and nni_model/data/FINGERPRINTS.csv
    (one row per file: path, bytes, sha256).

Outputs
    changed_files(): the files whose bytes or fingerprint differ from the
    stored row, and files with no row. An empty list means every file is
    as downloaded.

When data are downloaded again on purpose
    python -m nni_model.fingerprints --write
    rewrites FINGERPRINTS.csv; the change shows in the pull request.
"""

import csv
import hashlib
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data"
FINGERPRINT_FILE = DATA / "FINGERPRINTS.csv"


def fingerprint(path):
    """The SHA-256 fingerprint of a file's bytes, as 64 hexadecimal characters.

    Example:
        >>> len(fingerprint(DATA / "pwt" / "pwt110_hours.csv"))
        64
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raw_files(folder=DATA):
    """Every raw data file (CSV) under the data folder, as paths relative to it."""
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.csv")
                  if p.name != FINGERPRINT_FILE.name)


def read_fingerprints(path=FINGERPRINT_FILE):
    with open(path, encoding="utf-8", newline="") as f:
        return {row["path"]: row for row in csv.DictReader(f)}


def changed_files(folder=DATA, stored=None):
    """Files that differ from their stored fingerprint, or have none.

    Returns (path, problem) pairs; an empty list means all files are as downloaded.

    Example:
        >>> changed_files()
        []
    """
    stored = read_fingerprints() if stored is None else stored
    problems = []
    for name in raw_files(folder):
        row = stored.get(name)
        if row is None:
            problems.append((name, "no stored fingerprint"))
            continue
        path = folder / name
        if path.stat().st_size != int(row["bytes"]) or fingerprint(path) != row["sha256"]:
            problems.append((name, "bytes differ from the stored fingerprint"))
    for name in sorted(set(stored) - set(raw_files(folder))):
        problems.append((name, "file missing"))
    return problems


def write_fingerprints(folder=DATA, path=FINGERPRINT_FILE):
    """Rewrite the stored fingerprints after a deliberate new download."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256"])
        for name in raw_files(folder):
            writer.writerow([name, (folder / name).stat().st_size, fingerprint(folder / name)])


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_fingerprints()
        print(f"Wrote {FINGERPRINT_FILE.name}: {len(raw_files())} files")
    for name, problem in changed_files():
        print(f"{name}: {problem}")
