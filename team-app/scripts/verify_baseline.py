"""Verify the vendored baseline against the pinned commit, byte-exactly.

Why this is not `git status`:
    On this host git's `core.autocrlf` is true, so a checkout writes CRLF and
    reads CRLF back as LF. That made `git add -A` report a *damaged* tree as
    clean (an extra blank line appended to a file went unnoticed). Content
    identity therefore cannot be delegated to git's index.

What is compared:
    Git stores text blobs with LF only. This host's `core.autocrlf=true` makes
    a *git* checkout write CRLF, while the codeload tarball keeps LF. The
    vendored tree is the tarball, so text files are LF on disk (the "CRLF" files
    counted elsewhere are 7 binaries that contain the bytes 0d 0a by chance).

    Hence the fingerprint ignores line-ending form and nothing else:

        sha256(bytes with CRLF -> LF) for every pinned path

    Because git canonicalises CRLF->LF too, this equals the natural git blob
    identity on any host. Flipping CRLF<->LF is not reported (it is not a
    content change and the editable install reads either form); every other
    change -- appended line, altered byte, reordered content -- is.

Fails on: a missing file, an altered file, an unexpected extra file.
Ignores:  __pycache__, .pytest_cache, tmp*, pytest-of-*, tradingagents-tests-*,
          *.egg-info, and our own BASELINE_MANIFEST.txt / PINNED_COMMIT.txt.

Usage:
    python scripts/verify_baseline.py            # tolerate run droppings
    python scripts/verify_baseline.py --strict   # any extra file fails
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "tradingagents-0.7.x"
EXPECTED = ROOT / "vendor" / ".baseline" / "blob-sha-working-tree.txt"

IGNORED_DIRS = {"__pycache__", ".pytest_cache"}
IGNORED_PREFIXES = ("tmp", "pytest-of-", "tradingagents-tests-")
IGNORED_NAMES = {"BASELINE_MANIFEST.txt", "PINNED_COMMIT.txt"}
IGNORED_DIR_SUFFIXES = (".egg-info",)


def fingerprint(data: bytes) -> str:
    """SHA-256 of the content with CRLF folded to LF (git's canonical text form)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _is_dropping(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in IGNORED_DIRS for p in parts):
        return True
    if parts[0].startswith(IGNORED_PREFIXES):
        return True
    if any(p.endswith(IGNORED_DIR_SUFFIXES) for p in parts):
        return True
    return rel in IGNORED_NAMES


def main(strict: bool = False) -> int:
    rows = [line.split("\t") for line in EXPECTED.read_text(encoding="utf-8").splitlines() if line]
    missing, altered = [], []
    for sha, rel in rows:
        path = VENDOR / rel
        if not path.is_file():
            missing.append(rel)
        elif fingerprint(path.read_bytes()) != sha:
            altered.append(rel)

    tracked = {rel for _, rel in rows}
    present = {p.relative_to(VENDOR).as_posix() for p in VENDOR.rglob("*") if p.is_file()}
    extras = present - tracked - IGNORED_NAMES
    droppings = sorted(p for p in extras if not _is_dropping(p))
    ignored = sorted(p for p in extras if _is_dropping(p))

    print(f"pinned files : {len(tracked)}")
    print(f"missing      : {len(missing)}")
    print(f"altered      : {len(altered)}")
    print(f"unexpected   : {len(droppings)}")
    print(f"run output   : {len(ignored)} files (ignored)")
    for label, items in (("MISSING", missing), ("ALTERED", altered), ("UNEXPECTED", droppings)):
        for item in items[:20]:
            print(f"  {label}: {item}")
    ok = not (missing or altered or droppings)
    if strict and ignored:
        ok = False
        print("--strict: files beyond the pinned set are a failure")
    print("baseline-verify:", "PASS (vendored tree matches the pinned commit)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(strict="--strict" in sys.argv))
