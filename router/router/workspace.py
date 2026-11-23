"""Before/after snapshots of the folder a model works in, so the router can
(1) validate what an agentic attempt actually changed, not just what it said, and
(2) undo a failed attempt before the next one runs. Undo never deletes: files the
failed attempt created are moved to a stash folder, and overwritten files are
restored from the snapshot (the failed version is stashed too)."""

from __future__ import annotations

import difflib
import fcntl
import hashlib
import shutil
from contextlib import contextmanager
import time
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".build", "DerivedData", ".opencode"}
MAX_BYTES = 512 * 1024
MAX_FILES = 3000


@dataclass
class Changes:
    modified: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    diff: str = ""

    @property
    def any(self) -> bool:
        return bool(self.modified or self.created or self.deleted)

    def to_log(self) -> dict:
        return {k: v for k, v in (("modified", self.modified), ("created", self.created),
                                  ("deleted", self.deleted)) if v}


class FolderBusy(RuntimeError):
    pass


@contextmanager
def folder_lock(state_dir: Path, folder: str | Path):
    """One router run per working folder at a time. Two overlapping runs would see each
    other's edits as their own and could undo each other (found 2026-11-05 when two
    sample runs overlapped)."""
    # one shared lock folder, so runs with different state folders still exclude each other
    locks = Path(__file__).resolve().parent.parent / "state" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(Path(folder).resolve()).encode()).hexdigest()[:16]
    with open(locks / f"{key}.lock", "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise FolderBusy(f"another router run is already working in {folder}")
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def snapshot(root: str | Path) -> dict[str, bytes]:
    root = Path(root)
    snap: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if len(snap) >= MAX_FILES:
            break
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file() and not p.is_symlink():
            try:
                if p.stat().st_size <= MAX_BYTES:
                    snap[str(p.relative_to(root))] = p.read_bytes()
            except OSError:
                pass
    return snap


def compare(before: dict[str, bytes], root: str | Path, max_diff: int = 8000) -> Changes:
    after = snapshot(root)
    ch = Changes(
        modified=sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
        created=sorted(after.keys() - before.keys()),
        deleted=sorted(before.keys() - after.keys()),
    )
    parts = []
    for name in ch.modified + ch.created + ch.deleted:
        a = before.get(name, b"").decode("utf-8", "replace").splitlines(keepends=True)
        b = after.get(name, b"").decode("utf-8", "replace").splitlines(keepends=True)
        parts.append("".join(difflib.unified_diff(a, b, f"a/{name}", f"b/{name}")))
    ch.diff = "".join(parts)[:max_diff]
    return ch


def file_texts(root: str | Path, ch: Changes, max_chars: int = 12000) -> str:
    """The changed/created files as they are now, numbered, for the audit."""
    parts = []
    for name in ch.modified + ch.created:
        try:
            lines = (Path(root) / name).read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        parts.append(f"=== {name}\n" + "\n".join(f"{i:4} | {l}" for i, l in enumerate(lines, 1)))
    return "\n\n".join(parts)[:max_chars]


def rollback(before: dict[str, bytes], root: str | Path, ch: Changes, stash_root: Path) -> Path | None:
    if not ch.any:
        return None
    root = Path(root)
    stash = stash_root / time.strftime("%Y%m%d-%H%M%S")
    for name in ch.created + ch.modified:
        src = root / name
        if src.exists():
            dst = stash / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    for name in ch.modified + ch.deleted:
        dst = root / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(before[name])
    return stash
