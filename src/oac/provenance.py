"""Stamp every committed output with what produced it.

A deliberately smaller sibling of `opdi/benchmarks/provenance.py`. That one
also fingerprints S3 input tables, which needs boto3 and credentials; this one
runs offline, because the files it stamps are produced offline and a user
regenerating statistics from the committed per-flight table must not need a
cluster account to do it. The manifest format is the same, so
`opdi`'s `_manifest.json` and this one can be read by the same code.

Why it exists at all: this site renders from committed CSVs with no ability to
recompute them, and offline rendering is exactly the condition under which a
stale file renders cleanly and says nothing about being stale. An output with
no manifest entry is shown as **unverified** rather than as fact.
"""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = "_manifest.json"

__all__ = ["git_sha", "git_dirty", "file_hash", "fingerprint", "load_manifest",
           "save_manifest", "record"]


def _git(*args, cwd=None) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def git_sha(short: bool = True, cwd=None) -> str:
    return _git("rev-parse", "--short" if short else "HEAD", "HEAD", cwd=cwd) or "unknown"


def git_dirty(cwd=None) -> bool:
    return bool(_git("status", "--porcelain", cwd=cwd))


def file_hash(path) -> str:
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return h[:16]


def fingerprint(paths) -> str:
    """One hash over the *contents* of the code that produced an output.

    A git SHA alone says which commit was checked out, not whether the file was
    edited afterwards -- and a study is regenerated far more often from a dirty
    tree than from a clean one.
    """
    h = hashlib.sha256()
    for p in sorted(str(x) for x in paths):
        f = Path(p)
        h.update(p.encode())
        h.update(f.read_bytes() if f.is_file() else b"<missing>")
    return h.hexdigest()[:16]


def load_manifest(data_dir) -> dict:
    p = Path(data_dir) / MANIFEST
    return json.loads(p.read_text()) if p.is_file() else {}


def save_manifest(data_dir, manifest: dict) -> None:
    p = Path(data_dir) / MANIFEST
    p.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def record(data_dir, output: str, script: str, argv: list, code_paths: list,
           inputs: dict = None, notes: str = "") -> dict:
    """Add or replace one output's entry in the manifest.

    `inputs` maps a readable name to a row count or any scalar worth pinning.
    It is what makes "this was computed over three days" checkable rather than
    assumed.
    """
    data_dir = Path(data_dir)
    out_path = data_dir / output
    manifest = load_manifest(data_dir)
    entry = {
        "script": script,
        "argv": list(argv),
        "git_sha": git_sha(),
        "git_dirty": git_dirty(),
        "produced_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_fingerprint": fingerprint(code_paths),
        "code_paths": sorted(str(p) for p in code_paths),
        "inputs": inputs or {},
        "notes": notes,
    }
    if out_path.is_file():
        entry["sha256_16"] = file_hash(out_path)
        entry["bytes"] = out_path.stat().st_size
    manifest[output] = entry
    save_manifest(data_dir, manifest)
    return entry
