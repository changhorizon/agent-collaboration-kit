#!/usr/bin/env python3
"""Explicit, one-shot local collaboration helpers.

This tool is deliberately *not* a runtime gate, watcher, scheduler or delivery
service. Every command is invoked explicitly, reads bounded local inputs,
writes only inside a caller-chosen collaboration directory, and exits.

Message parsing, field/role/kind definitions and section extraction are loaded
directly from ``sandbox/verify_messages.py``. That file remains the single
source of truth; this module does not keep a second copy of those definitions.

Writes performed by this tool are limited to:

* a uniquely named message file under ``<task-dir>/messages/`` (publish);
* a caller-chosen ledger file (ledger);
* a caller-chosen manifest / evidence directory (preserve).

No write is intended to overwrite an existing original. Local rejection by
this tool does not prove that a real runtime prevents the same action.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import fnmatch
import hashlib
import importlib.util
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

KIT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = KIT_ROOT / "sandbox" / "verify_messages.py"


def _load_protocol():
    """Load the existing checker as a module instead of copying its rules."""
    if not PROTOCOL_PATH.is_file():
        raise RuntimeError(f"protocol module not found: {PROTOCOL_PATH}")
    spec = importlib.util.spec_from_file_location("collab_verify_messages", PROTOCOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load protocol module: {PROTOCOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROTOCOL = _load_protocol()
FIELDS = PROTOCOL.FIELDS
ROLES = PROTOCOL.ROLES
KINDS = PROTOCOL.KINDS
IDENTIFIER = PROTOCOL.IDENTIFIER
section = PROTOCOL.section
parse_message = PROTOCOL.parse

LEDGER_SCHEMA = "collab-ledger/1"
MANIFEST_SCHEMA = "collab-preserve-manifest/1"
ARCHIVE_SCHEMA = "collab-evidence-archive/1"
STATE_SCHEMA = "collab-state-projection/1"

LEDGER_STATUSES = ("reserved", "started", "settled", "unknown", "released")
CONSUMED_STATUSES = frozenset({"started", "settled", "unknown"})
NOTICE_KINDS = frozenset({"request", "advice", "review", "result", "delegation"})

DEFAULT_EXCLUDES = (
    ".git",
    ".git/**",
    "**/.git/**",
    "__pycache__",
    "**/__pycache__/**",
    "*.pyc",
    "*.pyo",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    ".DS_Store",
)


class CollabError(Exception):
    """A deterministic refusal or invalid input. The CLI exits non-zero."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Small filesystem / serialization helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_temp(directory: Path, prefix: str, data: bytes, mode: int = 0o600) -> Path:
    fd, name = tempfile.mkstemp(prefix=prefix, dir=str(directory))
    path = Path(name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        raise
    return path


def _atomic_create(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Create *path* without ever replacing an existing file."""
    directory = path.parent
    if not directory.is_dir() or directory.is_symlink():
        raise CollabError(f"destination directory is not usable: {directory}")
    temporary = _write_temp(directory, f".{path.name}.", data, mode)
    try:
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise CollabError(f"refusing to overwrite existing file: {path}") from error
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
    _fsync_dir(directory)


def _atomic_replace(path: Path, data: bytes, mode: int = 0o644) -> None:
    directory = path.parent
    if not directory.is_dir() or directory.is_symlink():
        raise CollabError(f"destination directory is not usable: {directory}")
    temporary = _write_temp(directory, f".{path.name}.", data, mode)
    try:
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
    _fsync_dir(directory)


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise CollabError(f"not a regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CollabError(f"cannot read JSON from {path}: {error}") from error


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


def _emit_json(value: Any) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


def _split_header(text: str) -> tuple[list[str], int]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise CollabError("message is missing the opening '---' header delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise CollabError("message is missing the closing '---' header delimiter") from error
    return lines, end


def _header_value(text: str, name: str) -> str | None:
    lines, end = _split_header(text)
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            if key == name:
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    try:
                        decoded = json.loads(value)
                    except json.JSONDecodeError:
                        return value
                    return decoded if isinstance(decoded, str) else str(decoded)
                if value.startswith("'") and value.endswith("'"):
                    return value[1:-1].replace("''", "'")
                return value
    return None


def _rewrite_header(text: str, updates: Mapping[str, str]) -> str:
    lines, end = _split_header(text)
    header = lines[1:end]
    found: set[str] = set()
    for index, line in enumerate(header):
        if ":" not in line:
            continue
        name = line.split(":", 1)[0]
        if name in updates:
            header[index] = f"{name}: {updates[name]}"
            found.add(name)
    inserts = [f"{name}: {value}" for name, value in updates.items() if name not in found]
    rebuilt = [lines[0], *header, *inserts, "---", *lines[end + 1 :]]
    trailing = "\n" if text.endswith(("\n", "\r")) else ""
    return "\n".join(rebuilt) + trailing


def _default_id_factory(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(16)}"


def _read_message_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CollabError(f"input is not a regular file: {path}")
    try:
        if path.stat().st_size > 1024 * 1024:
            raise CollabError(f"input message is larger than 1 MiB: {path}")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CollabError(f"cannot read input message {path}: {error}") from error


def _messages_directory(input_file: Path, task_dir: Path | None) -> Path:
    if task_dir is None:
        return input_file.resolve().parent
    task_dir = task_dir.resolve()
    if task_dir.is_symlink() or not task_dir.is_dir():
        raise CollabError(f"task directory does not exist or is a symlink: {task_dir}")
    if task_dir.name == "messages":
        return task_dir
    return task_dir / "messages"


def _scan_existing_ids(messages_dir: Path) -> dict[tuple[str, str], list[Path]]:
    found: dict[tuple[str, str], list[Path]] = {}
    for path in sorted(messages_dir.rglob("*.md")):
        try:
            message = parse_message(path)
        except (OSError, UnicodeError, ValueError) as error:
            raise CollabError(
                "existing message cannot be parsed; refusing to publish into an "
                f"ambiguous directory: {path}: {error}"
            ) from error
        found.setdefault(message.key, []).append(path)
    return found


def _validate_text(text: str) -> Any:
    """Validate one message without touching the destination directory."""
    with tempfile.TemporaryDirectory(prefix="collab-publish-") as directory:
        probe = Path(directory) / "message.md"
        probe.write_text(text, encoding="utf-8")
        try:
            return parse_message(probe)
        except (OSError, UnicodeError, ValueError) as error:
            raise CollabError(f"message validation failed: {error}") from error


def _validate_publish_directory(candidate_text: str, messages_dir: Path | None) -> dict[str, Any]:
    """Run the checker over the candidate plus a real-file copy of the task.

    ``verify_messages.validate`` is directory-level: it checks duplicate IDs,
    missing references, supersedes author/kind, cycles and the other rules that
    a single-message parse cannot see. Existing messages are copied as ordinary
    files (never symlinks) into an isolated directory so nothing is written to
    the real mailbox before the whole set passes.
    """
    with tempfile.TemporaryDirectory(prefix="collab-publish-set-") as temporary:
        root = Path(temporary)
        if messages_dir is not None and messages_dir.exists():
            for path in sorted(messages_dir.rglob("*.md")):
                if path.is_symlink() or not path.is_file():
                    raise CollabError(f"existing message is not a regular file: {path}")
                relative = path.relative_to(messages_dir)
                destination = root / "existing" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(path.read_bytes())
        candidate = root / "candidate" / "candidate.md"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(candidate_text, encoding="utf-8")
        count, tasks, errors = PROTOCOL.validate(root)
        if errors:
            labels = {
                str(root / "candidate"): "<candidate>",
                str(root / "existing"): str(messages_dir) if messages_dir is not None else "<existing>",
            }
            readable = []
            for error in errors:
                rendered = error
                for prefix, label in labels.items():
                    rendered = rendered.replace(prefix, label)
                readable.append(rendered)
            raise CollabError(
                "directory-level validation failed; refusing to publish: " + " | ".join(readable)
            )
        return {"messages": count, "tasks": tasks, "errors": []}


def publish(
    input_file: Path,
    task_dir: Path | None = None,
    from_role: str | None = None,
    id_factory: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Publish one fully validated message with a generated, unique ID.

    The candidate is first parsed alone, then checked together with a real-file
    copy of the existing task messages using ``verify_messages.validate``. The
    destination file is created atomically with a hard link, so an existing file
    is never replaced and an interrupted publish does not expose a half-written
    formal message.
    """
    input_file = Path(input_file)
    if from_role is not None and from_role not in ROLES:
        raise CollabError(f"unknown sender role: {from_role}")
    text = _read_message_text(input_file)
    declared_sender = from_role or _header_value(text, "from")
    if not declared_sender:
        raise CollabError("message header has no 'from' field and --from was not supplied")
    if declared_sender not in ROLES:
        raise CollabError(f"unknown sender role: {declared_sender}")

    factory = id_factory or _default_id_factory
    message_id = factory(declared_sender)
    if not isinstance(message_id, str) or not IDENTIFIER.fullmatch(message_id):
        raise CollabError(f"generated message ID is not a valid identifier: {message_id!r}")

    updates = {"id": message_id}
    if from_role is not None:
        updates["from"] = from_role
    candidate = _rewrite_header(text, updates)

    # Full structural validation happens before any file is placed in the
    # task's message directory.
    parsed = _validate_text(candidate)
    if parsed.header["id"] != message_id:
        raise CollabError("internal error: generated ID did not survive header rewrite")
    task = parsed.header["task"]

    messages_dir = _messages_directory(input_file, task_dir)
    if messages_dir.exists():
        if messages_dir.is_symlink() or not messages_dir.is_dir():
            raise CollabError(f"message directory is not usable: {messages_dir}")
        existing = _scan_existing_ids(messages_dir)
        if (task, message_id) in existing:
            paths = ", ".join(str(path) for path in existing[(task, message_id)])
            raise CollabError(f"message ID already exists in task {task}: {message_id} ({paths})")
    else:
        if messages_dir.parent.is_symlink() or not messages_dir.parent.is_dir():
            raise CollabError(f"cannot create message directory under: {messages_dir.parent}")

    # Run the directory-level checker over the candidate plus a real-file copy
    # of every existing message. This catches missing references, duplicate
    # IDs, invalid supersedes and cycles before anything is written.
    directory_validation = _validate_publish_directory(
        candidate, messages_dir if messages_dir.exists() else None
    )

    if not messages_dir.exists():
        try:
            messages_dir.mkdir()
        except FileExistsError:
            if messages_dir.is_symlink() or not messages_dir.is_dir():
                raise CollabError(f"message directory is not usable: {messages_dir}")

    target = messages_dir / (
        f"{message_id}_{parsed.header['from']}_to_{parsed.header['to']}_{parsed.header['kind']}.md"
    )
    if target.exists() or target.is_symlink():
        raise CollabError(f"refusing to overwrite existing message file: {target}")

    encoded = candidate.encode("utf-8")
    temporary = _write_temp(messages_dir, f".{message_id}.", encoded, 0o600)
    try:
        # Re-parse the exact bytes now on disk in the destination directory.
        try:
            written = parse_message(temporary)
        except (OSError, UnicodeError, ValueError) as error:
            raise CollabError(f"message validation failed: {error}") from error
        if written.key != (task, message_id):
            raise CollabError("internal error: message identity changed during publish")
        try:
            os.link(temporary, target)
        except FileExistsError as error:
            raise CollabError(f"refusing to overwrite existing message file: {target}") from error
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
    _fsync_dir(messages_dir)

    return {
        "status": "published",
        "task": task,
        "id": message_id,
        "path": str(target),
        "from": parsed.header["from"],
        "to": parsed.header["to"],
        "kind": parsed.header["kind"],
        "validation": (
            "structurally valid (verify_messages.parse) and directory-valid "
            "(verify_messages.validate over candidate + existing messages); "
            "runtime permissions, delivery and factual truth NOT verified"
        ),
        "directory_validation": directory_validation,
        "note": (
            "Explicit local publish only; no automatic delivery or runtime gate. "
            "The sender field is a declared author, not an authenticated identity."
        ),
    }


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------


def _ledger_path(task_dir: Path | None, ledger: Path | None) -> Path:
    if ledger is not None:
        return Path(ledger).resolve()
    base = Path(task_dir) if task_dir is not None else Path(".")
    return base.resolve() / "budget.json"


@contextlib.contextmanager
def _ledger_lock(path: Path, exclusive: bool = True):
    lock_path = path.with_name(path.name + ".lock")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise CollabError(f"ledger directory is not usable: {path.parent}")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _load_ledger(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CollabError(f"ledger unknown: not found: {path}")
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CollabError(f"ledger unknown: cannot parse {path}: {error}") from error
    if not isinstance(ledger, dict):
        raise CollabError("ledger unknown: top-level JSON value is not an object")
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise CollabError(f"ledger unknown: expected schema {LEDGER_SCHEMA!r}")
    if not isinstance(ledger.get("quota"), dict):
        raise CollabError("ledger unknown: missing or invalid 'quota'")
    if not isinstance(ledger.get("entries"), list):
        raise CollabError("ledger unknown: missing or invalid 'entries'")
    for role, value in ledger["quota"].items():
        if role not in ROLES or isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CollabError(f"ledger unknown: invalid quota for role {role!r}")
    for entry in ledger["entries"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("call_ref"), str)
            or not entry["call_ref"].strip()
            or entry.get("role") not in ROLES
            or entry.get("status") not in LEDGER_STATUSES
        ):
            raise CollabError("ledger unknown: malformed entry")
    return ledger


def _normalise_quota(raw: Mapping[str, Any]) -> dict[str, int]:
    quota: dict[str, int] = {}
    for role, value in raw.items():
        if role not in ROLES:
            raise CollabError(f"unknown role in baseline quota: {role}")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CollabError(f"quota for {role} must be a non-negative integer")
        quota[role] = value
    if not quota:
        raise CollabError("baseline quota must contain at least one role")
    return quota


def _parse_baseline_argument(baseline: str) -> tuple[dict[str, int], str | None, str | None]:
    try:
        value = json.loads(baseline)
    except json.JSONDecodeError as error:
        raise CollabError(f"--baseline is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise CollabError("--baseline must be a JSON object")
    if "quota" in value:
        raw_quota = value.get("quota")
        if not isinstance(raw_quota, dict):
            raise CollabError("--baseline 'quota' must be an object")
        return (
            _normalise_quota(raw_quota),
            value.get("baseline_ref"),
            value.get("parent_scope"),
        )
    return _normalise_quota(value), None, None


def _parse_quota_arguments(items: list[str]) -> dict[str, int]:
    quota: dict[str, int] = {}
    for item in items:
        if "=" not in item:
            raise CollabError(f"--quota must be ROLE=N, got: {item}")
        role, raw = item.split("=", 1)
        if role not in ROLES:
            raise CollabError(f"unknown role in --quota: {role}")
        try:
            value = int(raw)
        except ValueError as error:
            raise CollabError(f"--quota value is not an integer: {item}") from error
        if value < 0:
            raise CollabError(f"--quota value must be non-negative: {item}")
        quota[role] = value
    return quota


def ledger_init(
    task_dir: Path | None = None,
    quota: Mapping[str, Any] | None = None,
    baseline: str | None = None,
    quota_items: Sequence[str] = (),
    baseline_ref: str | None = None,
    parent_scope: str | None = None,
    ledger: Path | None = None,
) -> dict[str, Any]:
    path = _ledger_path(task_dir, ledger)
    merged: dict[str, int] = {}
    parsed_ref = None
    parsed_parent = None
    if baseline is not None:
        base_quota, parsed_ref, parsed_parent = _parse_baseline_argument(baseline)
        merged.update(base_quota)
    if quota is not None:
        merged.update(_normalise_quota(quota))
    merged.update(_parse_quota_arguments(list(quota_items)))
    if not merged:
        raise CollabError("ledger init needs --baseline or at least one --quota ROLE=N")
    record = {
        "schema": LEDGER_SCHEMA,
        "task_dir": str((Path(task_dir) if task_dir is not None else path.parent).resolve()),
        "baseline_ref": baseline_ref or parsed_ref,
        "parent_scope": parent_scope or parsed_parent,
        "created_at": _utc_now(),
        "quota": dict(sorted(merged.items())),
        "entries": [],
        "note": "Local ledger only; a local refusal is not a runtime dispatch gate.",
    }
    with _ledger_lock(path, exclusive=True):
        if path.exists() or path.is_symlink():
            raise CollabError(f"refusing to overwrite existing ledger: {path}")
        _atomic_create(path, _json_bytes(record), 0o600)
    return {"status": "initialized", "ledger": str(path), "quota": record["quota"], "note": record["note"]}


def _entry_counts(entries: list[Any], role: str) -> tuple[dict[str, int], list[str]]:
    counts = {status: 0 for status in LEDGER_STATUSES}
    warnings: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("role") != role:
            continue
        status = entry.get("status")
        if status not in counts:
            warnings.append(f"unknown ledger status for {entry.get('call_ref')!r}: {status!r}; counted as unknown")
            counts["unknown"] += 1
        else:
            counts[status] += 1
    return counts, warnings


def ledger_check(task_dir: Path | None = None, ledger: Path | None = None) -> dict[str, Any]:
    """Read-only ledger pre-check.

    The exit code is only a coarse signal: this function returns ``status``
    ``unknown`` or ``over`` (and the CLI exits 2) for unknown ledgers or any
    over-budget role. Callers must still read per-role ``status``/``remaining``.
    This is never a runtime dispatch gate.
    """
    path = _ledger_path(task_dir, ledger)
    base_report: dict[str, Any] = {
        "command": "ledger check",
        "ledger": str(path),
        "note": (
            "Read-only pre-check only. This is not a runtime gate: a local "
            "rejection does not prove that the runtime prevents role dispatch."
        ),
        "decision_hint": (
            "Read status/remaining per role. The CLI exits 2 for an unknown ledger or any "
            "over-budget role; exit 0 does not prove runtime dispatch was granted."
        ),
        "exit_policy": "0 = no unknown/over; 2 = unknown or any role over budget",
    }
    try:
        ledger = _load_ledger(path)
    except CollabError as error:
        return {**base_report, "status": "unknown", "reason": str(error)}
    quota = ledger["quota"]
    entries = ledger["entries"]
    roles = sorted(set(quota) | {entry.get("role") for entry in entries if isinstance(entry, dict)})
    per_role: dict[str, Any] = {}
    warnings: list[str] = []
    unknown = False
    any_over = False
    total_quota = 0
    total_remaining = 0
    for role in roles:
        raw_quota = quota.get(role)
        if role not in ROLES or isinstance(raw_quota, bool) or not isinstance(raw_quota, int) or raw_quota < 0:
            per_role[str(role)] = {
                "quota": "unknown",
                "settled": "unknown",
                "reserved": "unknown",
                "consumed": "unknown",
                "remaining": "unknown",
                "status": "unknown",
            }
            unknown = True
            warnings.append(f"role {role!r} has no usable quota; reported as unknown")
            continue
        counts, role_warnings = _entry_counts(entries, role)
        warnings.extend(role_warnings)
        consumed = sum(counts[status] for status in CONSUMED_STATUSES)
        remaining = raw_quota - consumed - counts["reserved"]
        status = "over" if remaining < 0 else ("exhausted" if remaining == 0 else "ok")
        if status == "over":
            any_over = True
        per_role[role] = {
            "quota": raw_quota,
            "settled": counts["settled"],
            "started": counts["started"],
            "unknown": counts["unknown"],
            "reserved": counts["reserved"],
            "released": counts["released"],
            "consumed_conservative": consumed,
            "remaining": remaining,
            "status": status,
        }
        total_quota += raw_quota
        total_remaining += remaining
    if unknown:
        overall = {"quota": "unknown", "remaining": "unknown", "status": "unknown"}
    else:
        overall = {
            "quota": total_quota,
            "remaining": total_remaining,
            "status": (
                "over"
                if any_over or total_remaining < 0
                else ("exhausted" if total_remaining == 0 else "ok")
            ),
        }
    if unknown:
        status = "unknown"
    elif any_over or total_remaining < 0:
        status = "over"
    elif total_remaining == 0:
        status = "exhausted"
    else:
        status = "ok"
    return {
        **base_report,
        "status": status,
        "overall": overall,
        "roles": per_role,
        "entry_count": len(entries),
        "warnings": warnings,
        "unknown_fields": _unknown_ledger_fields(ledger),
    }


def _unknown_ledger_fields(ledger: Mapping[str, Any]) -> list[str]:
    fields = []
    for name in ("baseline_ref", "parent_scope", "created_at"):
        if name not in ledger or ledger.get(name) in (None, ""):
            fields.append(name)
    return fields


def _find_entry(entries: list[Any], call_ref: str) -> dict[str, Any] | None:
    for entry in entries:
        if isinstance(entry, dict) and entry.get("call_ref") == call_ref:
            return entry
    return None


def _reserve_report(ledger: Mapping[str, Any], role: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    counts, _ = _entry_counts(ledger["entries"], role)  # type: ignore[arg-type]
    consumed = sum(counts[status] for status in CONSUMED_STATUSES)
    remaining = int(ledger["quota"][role]) - consumed - counts["reserved"]
    return {
        "status": "reserved",
        "role": role,
        "call_ref": entry.get("call_ref"),
        "entry_status": entry.get("status"),
        "remaining": remaining,
        "note": "Local reservation only; not a runtime dispatch gate.",
    }


def ledger_reserve(
    role: str,
    call_ref: str,
    task_dir: Path | None = None,
    ledger: Path | None = None,
    source: str = "cli",
) -> dict[str, Any]:
    if role not in ROLES:
        raise CollabError(f"unknown role: {role}")
    if not isinstance(call_ref, str) or not call_ref.strip():
        raise CollabError("call-ref must be a non-empty string")
    path = _ledger_path(task_dir, ledger)
    if path.is_symlink() or not path.is_file():
        raise CollabError(f"ledger unknown: not found: {path}")
    with _ledger_lock(path, exclusive=True):
        data = _load_ledger(path)
        quota = data["quota"]
        entries = data["entries"]
        if role not in quota:
            raise CollabError(f"role {role} is not in this ledger's quota; refusing to guess")
        existing = _find_entry(entries, call_ref)
        if existing is not None:
            if existing.get("role") != role:
                raise CollabError(
                    f"call-ref {call_ref!r} already belongs to role {existing.get('role')!r}; refusing to reuse"
                )
            report = _reserve_report(data, role, existing)
            report["status"] = "duplicate"
            report["note"] = "Idempotent retry: existing reservation returned; quota was not charged again."
            return report
        counts, _ = _entry_counts(entries, role)
        consumed = sum(counts[status] for status in CONSUMED_STATUSES)
        remaining = int(quota[role]) - consumed - counts["reserved"]
        if remaining <= 0:
            raise CollabError(
                f"reservation refused locally: role {role} has no remaining budget "
                f"(quota={quota[role]}, consumed={consumed}, reserved={counts['reserved']}); "
                "this is a local tool refusal, not proof of a runtime gate"
            )
        now = _utc_now()
        entry = {
            "call_ref": call_ref,
            "role": role,
            "status": "reserved",
            "reserved_at": now,
            "updated_at": now,
            "source": source,
            "transitions": [{"status": "reserved", "at": now, "source": source}],
        }
        entries.append(entry)
        _atomic_replace(path, _json_bytes(data), 0o600)
        return _reserve_report(data, role, entry)


def ledger_settle(
    role: str,
    call_ref: str,
    status: str = "settled",
    task_dir: Path | None = None,
    ledger: Path | None = None,
    source: str = "cli",
) -> dict[str, Any]:
    if role not in ROLES:
        raise CollabError(f"unknown role: {role}")
    if status not in {"started", "settled", "unknown"}:
        raise CollabError("settle --status must be started, settled or unknown")
    path = _ledger_path(task_dir, ledger)
    if path.is_symlink() or not path.is_file():
        raise CollabError(f"ledger unknown: not found: {path}")
    with _ledger_lock(path, exclusive=True):
        data = _load_ledger(path)
        entry = _find_entry(data["entries"], call_ref)
        if entry is None:
            raise CollabError(f"unknown call-ref in ledger: {call_ref}")
        if entry.get("role") != role:
            raise CollabError(
                f"call-ref {call_ref!r} belongs to role {entry.get('role')!r}, not {role!r}"
            )
        current = entry.get("status")
        if current == "released":
            raise CollabError(f"call-ref {call_ref!r} was released; it cannot be settled")
        if current == status:
            return {
                "status": "idempotent",
                "role": role,
                "call_ref": call_ref,
                "entry_status": current,
                "note": "No change; existing status returned.",
            }
        allowed = {
            "reserved": {"started", "settled", "unknown"},
            "started": {"settled", "unknown"},
            "unknown": {"started", "settled"},
            "settled": set(),
        }
        if status not in allowed.get(str(current), set()):
            raise CollabError(f"invalid ledger transition for {call_ref!r}: {current!r} -> {status!r}")
        now = _utc_now()
        entry["status"] = status
        entry["updated_at"] = now
        entry.setdefault("transitions", []).append({"status": status, "at": now, "source": source})
        _atomic_replace(path, _json_bytes(data), 0o600)
        return {
            "status": "updated",
            "role": role,
            "call_ref": call_ref,
            "entry_status": status,
            "note": "Cancelled or failed calls do not refund consumed budget automatically.",
        }


def ledger_release(
    role: str,
    call_ref: str,
    task_dir: Path | None = None,
    ledger: Path | None = None,
    source: str = "cli",
) -> dict[str, Any]:
    if role not in ROLES:
        raise CollabError(f"unknown role: {role}")
    path = _ledger_path(task_dir, ledger)
    if path.is_symlink() or not path.is_file():
        raise CollabError(f"ledger unknown: not found: {path}")
    with _ledger_lock(path, exclusive=True):
        data = _load_ledger(path)
        entry = _find_entry(data["entries"], call_ref)
        if entry is None:
            raise CollabError(f"unknown call-ref in ledger: {call_ref}")
        if entry.get("role") != role:
            raise CollabError(
                f"call-ref {call_ref!r} belongs to role {entry.get('role')!r}, not {role!r}"
            )
        current = entry.get("status")
        if current == "released":
            return {
                "status": "idempotent",
                "role": role,
                "call_ref": call_ref,
                "entry_status": "released",
                "note": "Already released; no change.",
            }
        if current != "reserved":
            raise CollabError(
                f"refusing to release call-ref {call_ref!r}: status is {current!r}, "
                "but only an unstarted 'reserved' entry may be released"
            )
        now = _utc_now()
        entry["status"] = "released"
        entry["updated_at"] = now
        entry.setdefault("transitions", []).append({"status": "released", "at": now, "source": source})
        _atomic_replace(path, _json_bytes(data), 0o600)
        return {
            "status": "released",
            "role": role,
            "call_ref": call_ref,
            "entry_status": "released",
            "note": "Released only because the reservation had not started; no consumed budget was refunded.",
        }


# ---------------------------------------------------------------------------
# preserve: candidate manifest and evidence archive
# ---------------------------------------------------------------------------


def _pattern_matches(relative: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    if fnmatch.fnmatchcase(relative, pattern.rstrip("/") + "/**"):
        return True
    if "/" not in pattern:
        return any(fnmatch.fnmatchcase(part, pattern) for part in relative.split("/"))
    return False


def _is_excluded(relative: str, patterns: Sequence[str]) -> str | None:
    for pattern in patterns:
        if _pattern_matches(relative, pattern):
            return pattern
    return None


def _declared_relative(base: Path, raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    absolute = Path(os.path.abspath(candidate if candidate.is_absolute() else base / candidate))
    try:
        relative = absolute.relative_to(base)
    except ValueError as error:
        raise CollabError(f"declared path escapes the base directory: {raw}") from error
    if relative == Path("."):
        raise CollabError(f"base directory itself is not a file candidate: {raw}")
    # Reject a parent-directory symlink that resolves outside the base, but keep
    # the final component's symlink identity intact for type/mode recording.
    try:
        absolute.resolve().relative_to(base)
    except ValueError as error:
        raise CollabError(f"declared path resolves outside the base directory: {raw}") from error
    return absolute, relative.as_posix()


def _git_metadata(base: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "available": False,
        "head": None,
        "dirty_worktree": None,
        "tracked_files": None,
    }
    try:
        probe = subprocess.run(
            ["git", "-C", str(base), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return metadata
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return metadata
    metadata["available"] = True
    head = subprocess.run(
        ["git", "-C", str(base), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode == 0:
        metadata["head"] = head.stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(base), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode == 0:
        metadata["dirty_worktree"] = bool(status.stdout.strip())
    tracked = subprocess.run(
        ["git", "-C", str(base), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode == 0:
        metadata["tracked_files"] = {item for item in tracked.stdout.split("\0") if item}
    return metadata


def _file_identity(
    resolved: Path,
    relative: str,
    declared_as: str,
    tracked_files: set[str] | None,
) -> dict[str, Any]:
    base_record: dict[str, Any] = {
        "path": relative,
        "declared_as": declared_as,
        "tracked": (relative in tracked_files) if tracked_files is not None else None,
    }
    if not resolved.exists() and not resolved.is_symlink():
        return {
            **base_record,
            "type": "missing",
            "deleted": True,
            "mode": None,
            "size": None,
            "sha256": None,
        }
    info = resolved.lstat()
    mode = oct(stat.S_IMODE(info.st_mode))
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(resolved)
        return {
            **base_record,
            "type": "symlink",
            "deleted": False,
            "mode": mode,
            "size": len(target.encode("utf-8")),
            "sha256": _sha256_bytes(target.encode("utf-8")),
            "sha256_scope": "symlink-target-text",
            "link_target": target,
        }
    if not stat.S_ISREG(info.st_mode):
        raise CollabError(f"unsupported candidate type (list regular files): {resolved}")
    return {
        **base_record,
        "type": "file",
        "deleted": False,
        "mode": mode,
        "size": info.st_size,
        "sha256": _sha256_file(resolved),
    }


def _manifest_digest(manifest: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(canonical)


def preserve_manifest(
    base: Path,
    files: Sequence[str],
    untracked: Sequence[str] = (),
    excludes: Sequence[str] = (),
    out: Path | None = None,
    want_sha256: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Build a deterministic candidate identity manifest.

    Missing declared files are marked as deleted. If the base is a Git
    repository, HEAD/worktree identity and tracked status are added; these are
    inputs, not proof that tests ran or that the candidate set is complete.
    """
    base = Path(base).resolve()
    if base.is_symlink() or not base.is_dir():
        raise CollabError(f"base is not a directory: {base}")
    patterns = list(DEFAULT_EXCLUDES) + list(excludes)
    git = _git_metadata(base)
    tracked_files = git.get("tracked_files")
    entries: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in list(files) + list(untracked):
        declared_as = "file" if raw in files else "untracked"
        resolved, relative = _declared_relative(base, raw)
        if relative in seen:
            raise CollabError(f"duplicate candidate path: {relative}")
        seen.add(relative)
        matched = _is_excluded(relative, patterns)
        if matched is not None:
            excluded.append({"path": relative, "pattern": matched})
            continue
        entries.append(_file_identity(resolved, relative, declared_as, tracked_files))

    entries.sort(key=lambda item: item["path"])
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "base": str(base),
        "base_identity": {
            "git_head": git.get("head"),
            "git_dirty_worktree": git.get("dirty_worktree"),
            "git_available": git.get("available"),
            "note": (
                "Git HEAD plus tracked-worktree dirty state; untracked files are represented "
                "separately in the file list. This does not prove the candidate set is complete."
            ),
        },
        "generated_at": _utc_now(),
        "exclude_patterns": patterns,
        "files": entries,
        "excluded": excluded,
        "notes": [
            "Missing declared files are marked deleted.",
            "sha256 is content identity only; it does not prove tests ran.",
            "Symlink hashes cover the link target text, not the followed target.",
        ],
    }
    if want_sha256:
        manifest["manifest_sha256"] = _manifest_digest(manifest)

    if out is not None:
        out = Path(out)
        out_resolved = out.resolve()
        for raw in list(files) + list(untracked):
            candidate, _ = _declared_relative(base, raw)
            if candidate.resolve() == out_resolved:
                raise CollabError("--out must not be one of the declared candidate files")
        if out.exists() or out.is_symlink():
            if not force:
                raise CollabError(f"refusing to overwrite existing manifest: {out} (use --force)")
            try:
                existing = _read_json(out)
            except CollabError as error:
                raise CollabError(
                    f"refusing to overwrite a non-manifest file even with --force: {out}: {error}"
                ) from error
            if not isinstance(existing, dict) or existing.get("schema") != MANIFEST_SCHEMA:
                raise CollabError(f"refusing to overwrite a non-manifest file even with --force: {out}")
            _atomic_replace(out, _json_bytes(manifest), 0o644)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            _atomic_create(out, _json_bytes(manifest), 0o644)
    return manifest


def _git_baseline_check(manifest: Mapping[str, Any], base: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compare recorded Git HEAD/dirty state with the current base.

    A missing recorded baseline is reported as unknown, not as a pass. A
    recorded baseline that can no longer be observed, or that differs, is a
    mismatch.
    """
    recorded_raw = manifest.get("base_identity")
    recorded = recorded_raw if isinstance(recorded_raw, dict) else {}
    current_meta = _git_metadata(base)
    current = {
        "git_available": current_meta.get("available") is True,
        "git_head": current_meta.get("head"),
        "git_dirty_worktree": current_meta.get("dirty_worktree"),
    }
    recorded_available = recorded.get("git_available") is True
    recorded_head = recorded.get("git_head")
    recorded_dirty = recorded.get("git_dirty_worktree")
    mismatches: list[dict[str, Any]] = []
    if not recorded_available:
        status = "unknown"
        note = (
            "Manifest recorded no Git baseline; file identities were checked, but repository "
            "HEAD/dirty state was not verified."
        )
    elif not current["git_available"]:
        status = "mismatch"
        note = "Manifest recorded a Git baseline, but the current base is not a Git worktree."
        mismatches.append(
            {
                "path": None,
                "reason": "git baseline unavailable",
                "expected": recorded_head,
                "actual": None,
            }
        )
    else:
        if current["git_head"] is None:
            mismatches.append(
                {"path": None, "reason": "git HEAD unavailable", "expected": recorded_head, "actual": None}
            )
        elif current["git_head"] != recorded_head:
            mismatches.append(
                {
                    "path": None,
                    "reason": "git HEAD mismatch",
                    "expected": recorded_head,
                    "actual": current["git_head"],
                }
            )
        if current["git_dirty_worktree"] is None:
            mismatches.append(
                {
                    "path": None,
                    "reason": "git dirty-worktree state unavailable",
                    "expected": recorded_dirty,
                    "actual": None,
                }
            )
        elif current["git_dirty_worktree"] != recorded_dirty:
            mismatches.append(
                {
                    "path": None,
                    "reason": "git dirty-worktree state mismatch",
                    "expected": recorded_dirty,
                    "actual": current["git_dirty_worktree"],
                }
            )
        status = "mismatch" if mismatches else "match"
        note = (
            "Git HEAD and dirty-worktree state match the manifest."
            if not mismatches
            else "Git baseline changed or became unavailable."
        )
    report = {
        "status": status,
        "recorded": {
            "git_available": recorded_available,
            "git_head": recorded_head,
            "git_dirty_worktree": recorded_dirty,
        },
        "current": current,
        "note": note,
    }
    return report, mismatches


def verify_manifest(manifest_path: Path, base_override: Path | None = None) -> dict[str, Any]:
    """Recompute file identities plus the recorded Git baseline.

    Status values:
    * ``ok``: checked identities and recorded Git baseline both match.
    * ``ok-with-unknown-baseline``: file identities match, but the manifest has
      no usable Git baseline. Do not present this as full repository validation.
    * ``mismatch``: at least one identity/Git comparison failed.
    """
    manifest_path = Path(manifest_path)
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise CollabError(f"not a {MANIFEST_SCHEMA} manifest: {manifest_path}")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise CollabError("manifest is missing a valid 'files' list")
    raw_base = manifest.get("base")
    if base_override is None and (not isinstance(raw_base, str) or not raw_base.strip()):
        raise CollabError("manifest is missing a valid 'base'")
    base = Path(base_override).resolve() if base_override is not None else Path(raw_base).resolve()
    if not base.is_dir() or base.is_symlink():
        raise CollabError(f"manifest base is not an available directory: {base}")
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for item in raw_files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            mismatches.append({"path": None, "reason": "malformed manifest entry"})
            continue
        checked += 1
        relative = item["path"]
        try:
            resolved, _ = _declared_relative(base, relative)
        except CollabError as error:
            mismatches.append({"path": relative, "reason": str(error)})
            continue
        expected_type = item.get("type")
        expected_sha = item.get("sha256")
        expected_deleted = bool(item.get("deleted"))
        exists = resolved.exists() or resolved.is_symlink()
        if expected_deleted:
            if exists:
                mismatches.append({"path": relative, "reason": "was marked deleted but now exists"})
            continue
        if not exists:
            mismatches.append({"path": relative, "reason": "missing"})
            continue
        if not expected_sha:
            mismatches.append({"path": relative, "reason": "manifest has no content identity (sha256)"})
            continue
        info = resolved.lstat()
        if expected_type == "symlink":
            if not stat.S_ISLNK(info.st_mode):
                mismatches.append({"path": relative, "reason": "type changed (expected symlink)"})
                continue
            target = os.readlink(resolved)
            actual_sha = _sha256_bytes(target.encode("utf-8"))
        elif expected_type == "file":
            if not stat.S_ISREG(info.st_mode):
                mismatches.append({"path": relative, "reason": "type changed (expected regular file)"})
                continue
            actual_sha = _sha256_file(resolved)
        else:
            mismatches.append({"path": relative, "reason": f"unsupported manifest type: {expected_type!r}"})
            continue
        if actual_sha != expected_sha:
            mismatches.append(
                {
                    "path": relative,
                    "reason": "sha256 mismatch",
                    "expected": expected_sha,
                    "actual": actual_sha,
                }
            )
        if item.get("mode") is not None and oct(stat.S_IMODE(info.st_mode)) != item.get("mode"):
            mismatches.append(
                {
                    "path": relative,
                    "reason": "mode mismatch",
                    "expected": item.get("mode"),
                    "actual": oct(stat.S_IMODE(info.st_mode)),
                }
            )
    digest_note = None
    if "manifest_sha256" in manifest:
        actual_digest = _manifest_digest(manifest)
        if actual_digest != manifest["manifest_sha256"]:
            mismatches.append(
                {
                    "path": None,
                    "reason": "manifest_sha256 mismatch",
                    "expected": manifest["manifest_sha256"],
                    "actual": actual_digest,
                }
            )
        digest_note = "manifest self-digest checked"
    git_identity, git_mismatches = _git_baseline_check(manifest, base)
    mismatches.extend(git_mismatches)
    if mismatches:
        status = "mismatch"
    elif git_identity["status"] == "unknown":
        status = "ok-with-unknown-baseline"
    else:
        status = "ok"
    return {
        "status": status,
        "manifest": str(manifest_path),
        "base": str(base),
        "checked": checked,
        "mismatches": mismatches,
        "digest": digest_note,
        "git_identity": git_identity,
        "note": (
            "A mismatch means the candidate identity or recorded Git baseline changed, or a "
            "required identity is unknown. An unknown baseline is not a full validation. Do not "
            "present an old report as validation of this candidate; runtime bypass remains unverified."
        ),
    }


def preserve_archive(
    return_file: Path,
    original_author: str,
    transcribed_by: str,
    call_ref: str,
    version: str,
    redaction: str | None = None,
    out: Path | None = None,
) -> dict[str, Any]:
    """Copy an original role return plus honest transcription metadata.

    The copy is byte-for-byte. The metadata records both the original author and
    the transcriber; this tool never turns a transcription into an original
    publication.
    """
    source = Path(return_file)
    if source.is_symlink() or not source.is_file():
        raise CollabError(f"return file is not a regular file: {source}")
    if original_author not in ROLES:
        raise CollabError(f"unknown original author role: {original_author}")
    if transcribed_by not in ROLES:
        raise CollabError(f"unknown transcriber role: {transcribed_by}")
    for name, value in (("call-ref", call_ref), ("version", version)):
        if not isinstance(value, str) or not value.strip():
            raise CollabError(f"{name} must be a non-empty string")
    destination = Path(out) if out is not None else Path.cwd() / ".agent" / "evidence"
    destination = destination.resolve()
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir():
            raise CollabError(f"evidence destination is not a usable directory: {destination}")
    else:
        destination.mkdir(parents=True, exist_ok=True)
    target = destination / source.name
    metadata_path = destination / (source.name + ".meta.json")
    if source.resolve() == target:
        raise CollabError("refusing to archive a file onto itself")
    if target.exists() or target.is_symlink():
        raise CollabError(f"refusing to overwrite existing evidence file: {target}")
    if metadata_path.exists() or metadata_path.is_symlink():
        raise CollabError(f"refusing to overwrite existing evidence metadata: {metadata_path}")

    content = source.read_bytes()
    content_sha = _sha256_bytes(content)
    metadata = {
        "schema": ARCHIVE_SCHEMA,
        "original_file": str(source.resolve()),
        "archived_file": str(target),
        "original_author": original_author,
        "transcribed_by": transcribed_by,
        "author_is_transcriber": original_author == transcribed_by,
        "call_ref": call_ref,
        "version": version,
        "redaction": redaction,
        "archived_at": _utc_now(),
        "content_sha256": content_sha,
        "byte_size": len(content),
        "note": (
            "Byte-for-byte transcription. original_author is the declared author of the "
            "return; transcribed_by is the role that copied it. This is not a new original "
            "publication or an authentication of the author."
        ),
    }
    data_tmp = _write_temp(destination, f".{target.name}.", content, 0o600)
    meta_tmp = _write_temp(destination, f".{metadata_path.name}.", _json_bytes(metadata), 0o600)
    try:
        try:
            os.link(data_tmp, target)
        except FileExistsError as error:
            raise CollabError(f"refusing to overwrite existing evidence file: {target}") from error
        try:
            os.link(meta_tmp, metadata_path)
        except FileExistsError as error:
            with contextlib.suppress(FileNotFoundError):
                target.unlink()
            raise CollabError(f"refusing to overwrite existing evidence metadata: {metadata_path}") from error
    finally:
        for temporary in (data_tmp, meta_tmp):
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
    _fsync_dir(destination)
    return {
        "status": "archived",
        "archived_file": str(target),
        "metadata": str(metadata_path),
        "content_sha256": content_sha,
        "original_author": original_author,
        "transcribed_by": transcribed_by,
        "note": "Transcription preserved as a copy; it is not an original role publication.",
    }


# ---------------------------------------------------------------------------
# state projection
# ---------------------------------------------------------------------------


def _is_cancelled(message: Any) -> bool:
    return (
        message.header["kind"] in {"request", "delegation"}
        and section(message.body, "指令状态") == "cancelled"
    )


def _find_cycles(nodes: set[tuple[str, str]], edges: Mapping[tuple[str, str], set[tuple[str, str]]]):
    color: dict[tuple[str, str], int] = {node: 0 for node in nodes}
    stack: list[tuple[str, str]] = []
    cycles: list[list[tuple[str, str]]] = []
    seen_cycles: set[frozenset[tuple[str, str]]] = set()

    def visit(node: tuple[str, str]) -> None:
        color[node] = 1
        stack.append(node)
        for target in edges.get(node, set()):
            if target not in color:
                continue
            if color[target] == 0:
                visit(target)
            elif color[target] == 1:
                index = stack.index(target)
                cycle = stack[index:] + [target]
                signature = frozenset(cycle)
                if signature not in seen_cycles:
                    seen_cycles.add(signature)
                    cycles.append(cycle)
        stack.pop()
        color[node] = 2

    for node in sorted(nodes):
        if color[node] == 0:
            visit(node)
    return cycles


class _DSU:
    def __init__(self, nodes: set[tuple[str, str]]):
        self.parent = {node: node for node in nodes}

    def find(self, node: tuple[str, str]) -> tuple[str, str]:
        parent = self.parent[node]
        if parent != node:
            self.parent[node] = self.find(parent)
        return self.parent[node]

    def union(self, left: tuple[str, str], right: tuple[str, str]) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[b] = a


def _state_location(task_dir: Path) -> tuple[Path, Path]:
    task_dir = Path(task_dir).resolve()
    if not task_dir.is_dir() or task_dir.is_symlink():
        raise CollabError(f"task directory does not exist or is a symlink: {task_dir}")
    messages_dir = task_dir / "messages"
    if not messages_dir.is_dir():
        messages_dir = task_dir
    if messages_dir.is_symlink() or not messages_dir.is_dir():
        raise CollabError(f"messages directory is not usable: {messages_dir}")
    return task_dir, messages_dir


def derive_state(task_dir: Path, include_protocol_check: bool = True) -> dict[str, Any]:
    """Derive a disposable projection; never infer authorization or budget."""
    task_dir, messages_dir = _state_location(task_dir)
    parsed: list[Any] = []
    parse_errors: list[str] = []
    input_fingerprint: list[dict[str, Any]] = []
    for path in sorted(messages_dir.rglob("*.md")):
        try:
            parsed.append(parse_message(path))
        except (OSError, UnicodeError, ValueError) as error:
            parse_errors.append(f"{path}: {error}")
        with contextlib.suppress(OSError):
            info = path.lstat()
            input_fingerprint.append(
                {
                    "path": str(path),
                    "size": info.st_size,
                    "mtime_ns": info.st_mtime_ns,
                    "sha256": (
                        _sha256_file(path)
                        if path.is_file() and not path.is_symlink() and info.st_size <= 1024 * 1024
                        else None
                    ),
                }
            )

    by_key: dict[tuple[str, str], list[Any]] = {}
    for message in parsed:
        by_key.setdefault(message.key, []).append(message)
    first_by_key = {key: messages[0] for key, messages in by_key.items()}
    duplicates = {
        key: [str(message.path) for message in messages]
        for key, messages in by_key.items()
        if len(messages) > 1
    }

    edges: dict[tuple[str, str], set[tuple[str, str]]] = {key: set() for key in first_by_key}
    supersede_edges: dict[tuple[str, str], set[tuple[str, str]]] = {key: set() for key in first_by_key}
    super_parent: dict[tuple[str, str], tuple[str, str]] = {}
    super_children: dict[tuple[str, str], set[tuple[str, str]]] = {}
    reference_gaps: list[dict[str, str]] = []
    conflicts: list[dict[str, Any]] = []
    cross_author: list[dict[str, Any]] = []
    conflict_lineage: set[tuple[str, str]] = set()

    def ancestors(key: tuple[str, str]) -> set[tuple[str, str]]:
        result: set[tuple[str, str]] = set()
        current = super_parent.get(key)
        while current is not None and current not in result:
            result.add(current)
            current = super_parent.get(current)
        return result

    def descendants(key: tuple[str, str]) -> set[tuple[str, str]]:
        return {candidate for candidate in first_by_key if key in ancestors(candidate)}

    def mark(key: tuple[str, str]) -> None:
        conflict_lineage.add(key)
        conflict_lineage.update(ancestors(key))
        conflict_lineage.update(descendants(key))

    for message in parsed:
        key = message.key
        task = message.header["task"]
        for field in ("reply_to", "supersedes"):
            value = message.header[field]
            if value == "null":
                continue
            target = (task, value)
            if target not in first_by_key:
                gap = {
                    "path": str(message.path),
                    "message": message.header["id"],
                    "field": field,
                    "target": value,
                    "reason": f"{field} target is missing from the task",
                }
                reference_gaps.append(gap)
                conflicts.append({"kind": "missing_reference", **gap})
                mark(key)
                continue
            edges[key].add(target)
            if field == "supersedes":
                supersede_edges[key].add(target)
                super_children.setdefault(target, set()).add(key)
                super_parent.setdefault(key, target)
                parent = first_by_key[target]
                if message.header["from"] != parent.header["from"] or message.header["kind"] != parent.header["kind"]:
                    detail = {
                        "kind": "cross_author_supersede",
                        "message": message.header["id"],
                        "path": str(message.path),
                        "target": value,
                        "reason": "supersedes must keep the same author and kind",
                    }
                    cross_author.append(detail)
                    conflicts.append(detail)
                    mark(target)
                    mark(key)

    for key, paths in duplicates.items():
        conflicts.append(
            {
                "kind": "duplicate_id",
                "task": key[0],
                "message": key[1],
                "paths": paths,
                "reason": "the same task+id appears more than once; references are ambiguous",
            }
        )
        mark(key)
        for message in parsed:
            if message.header["task"] != key[0]:
                continue
            if message.header["reply_to"] == key[1] or message.header["supersedes"] == key[1]:
                mark(message.key)

    cycles = _find_cycles(set(first_by_key), edges)
    for cycle in cycles:
        readable = [f"{task}/{message_id}" for task, message_id in cycle]
        conflicts.append(
            {
                "kind": "reference_cycle",
                "cycle": readable,
                "reason": "reply_to/supersedes cycle; no timestamp-based winner is chosen",
            }
        )
        for key in cycle:
            mark(key)

    for target, children in super_children.items():
        if len(children) == 1:
            continue
        maximal = {
            child
            for child in children
            if not any(child in ancestors(other) for other in children if other != child)
        }
        if len(maximal) > 1:
            conflicts.append(
                {
                    "kind": "multiple_successors",
                    "target": f"{target[0]}/{target[1]}",
                    "successors": sorted(f"{key[0]}/{key[1]}" for key in children),
                    "maximal_successors": sorted(f"{key[0]}/{key[1]}" for key in maximal),
                    "reason": "one message has mutually incompatible successors; no winner is chosen",
                }
            )
            for key in {target, *children}:
                mark(key)

    def delivery_for(message: Any) -> dict[str, Any]:
        receipts = [
            candidate
            for candidate in parsed
            if candidate.header["kind"] == "received"
            and candidate.header["task"] == message.header["task"]
            and candidate.header["reply_to"] == message.header["id"]
        ]
        return {
            "task": message.header["task"],
            "id": message.header["id"],
            "path": str(message.path),
            "status": "confirmed" if receipts else "unconfirmed",
            "received_by": [
                {
                    "id": receipt.header["id"],
                    "from": receipt.header["from"],
                    "path": str(receipt.path),
                    "created_at": receipt.header["created_at"],
                }
                for receipt in receipts
            ],
            "note": (
                "Exact reply_to received message(s) exist."
                if receipts
                else "No exact received reference; this is unconfirmed delivery/hand-off, not proof of non-delivery."
            ),
        }

    delivery = [delivery_for(message) for message in parsed]
    delivery_by_id = {item["id"]: item for item in delivery}

    dsu = _DSU(set(first_by_key))
    for left, targets in edges.items():
        for right in targets:
            if right in dsu.parent:
                dsu.union(left, right)

    entries: list[dict[str, Any]] = []
    superseded_history: list[dict[str, Any]] = []
    for key in sorted(first_by_key, key=lambda item: (item[0], item[1])):
        message = first_by_key[key]
        if key in super_children:
            superseded_history.append(
                {
                    "task": key[0],
                    "id": key[1],
                    "path": str(message.path),
                    "from": message.header["from"],
                    "to": message.header["to"],
                    "kind": message.header["kind"],
                    "created_at": message.header["created_at"],
                    "status": "superseded",
                    "superseded_by": sorted(f"{item[0]}/{item[1]}" for item in super_children[key]),
                    "retained_as": "referenced_technical_body",
                    "conflict": key in conflict_lineage,
                    "note": (
                        "Not a current entry. Retained so a newer entry can still reference its technical body; "
                        "a withdrawal must not revive an older ancestor."
                    ),
                }
            )
            continue
        if key in duplicates or key in conflict_lineage:
            status = "conflict"
        elif _is_cancelled(message):
            status = "cancelled"
        else:
            status = "current"
        ancestors_records = []
        for ancestor in sorted(ancestors(key)):
            if ancestor in first_by_key:
                older = first_by_key[ancestor]
                ancestors_records.append(
                    {
                        "task": ancestor[0],
                        "id": ancestor[1],
                        "path": str(older.path),
                        "kind": older.header["kind"],
                        "from": older.header["from"],
                        "status": "superseded",
                        "retained_as": "referenced_technical_body",
                    }
                )
        entry = {
            "task": key[0],
            "id": key[1],
            "path": str(message.path),
            "from": message.header["from"],
            "to": message.header["to"],
            "kind": message.header["kind"],
            "created_at": message.header["created_at"],
            "status": status,
            "cancelled": _is_cancelled(message),
            "component": f"{dsu.find(key)[0]}/{dsu.find(key)[1]}",
            "superseded_ancestors": ancestors_records,
            "delivery": delivery_by_id.get(message.header["id"]),
            "executability": "unknown",
        }
        entries.append(entry)

    executable_notices = []
    for entry in entries:
        if entry["status"] != "current" or entry["kind"] not in NOTICE_KINDS:
            continue
        executable_notices.append(
            {
                "task": entry["task"],
                "id": entry["id"],
                "path": entry["path"],
                "from": entry["from"],
                "to": entry["to"],
                "kind": entry["kind"],
                "executability": "unknown",
                "notice": (
                    "Current entry candidate. Lead must verify authorization, budget, pause state and the "
                    "referenced originals before treating this as actionable."
                ),
                "caveats": [
                    "This projection is not authorization.",
                    "No runtime gate, delivery or author identity was verified here.",
                    "Pending user decisions remain unknown unless Lead checks the originals.",
                ],
            }
        )

    protocol_check: dict[str, Any] | None = None
    if include_protocol_check:
        try:
            count, tasks, errors = PROTOCOL.validate(messages_dir)
            protocol_check = {"messages": count, "tasks": tasks, "errors": errors}
        except Exception as error:  # The projection must remain inspectable.
            protocol_check = {"messages": 0, "tasks": 0, "errors": [f"checker failed: {error}"]}

    unconfirmed = [item for item in delivery if item["status"] == "unconfirmed"]
    return {
        "schema": STATE_SCHEMA,
        "tool": (
            "Explicit local state projection. Derived and disposable; rebuild when inputs change. "
            "It is not a second authority, a runtime gate or an authorization record."
        ),
        "task_dir": str(task_dir),
        "messages_dir": str(messages_dir),
        "generated_at": _utc_now(),
        "input_fingerprint": input_fingerprint,
        "parse_errors": parse_errors,
        "protocol_check": protocol_check,
        "summary": {
            "messages": len(parsed),
            "current_entries": sum(1 for entry in entries if entry["status"] == "current"),
            "cancelled_entries": sum(1 for entry in entries if entry["status"] == "cancelled"),
            "conflict_entries": sum(1 for entry in entries if entry["status"] == "conflict"),
            "superseded_messages": len(superseded_history),
            "executable_notices": len(executable_notices),
            "unconfirmed_delivery": len(unconfirmed),
            "conflicts": len(conflicts),
            "reference_gaps": len(reference_gaps),
        },
        "entries": entries,
        "superseded_history": superseded_history,
        "delivery": delivery,
        "executable_notices": executable_notices,
        "conflicts": conflicts,
        "reference_gaps": reference_gaps,
        "duplicate_ids": [
            {"task": key[0], "id": key[1], "paths": paths} for key, paths in sorted(duplicates.items())
        ],
        "cycles": [[f"{task}/{message_id}" for task, message_id in cycle] for cycle in cycles],
        "executability": {
            "status": "unknown",
            "authorization": "unknown",
            "budget": "unknown",
            "pause": "unknown",
            "note": "Only Lead can maintain these after checking originals; this tool does not infer them.",
        },
        "unknown_facts": {
            "author_identity": "unknown",
            "delivery_completeness": "unknown",
            "deletion_history": "unknown",
            "authorization": "unknown",
            "budget": "unknown",
            "pause_state": "unknown",
        },
        "notes": [
            "Current entries are grouped by same-author/same-kind supersede lineage, not by a global latest timestamp.",
            "Superseded originals stay visible as referenced technical bodies.",
            "Conflicts suppress executable notices for the affected lineage only; unrelated chains remain visible.",
            "No timestamp-based winner selection is performed.",
        ],
    }


def _format_state_text(state: Mapping[str, Any]) -> str:
    lines = [
        f"task_dir: {state['task_dir']}",
        f"messages_dir: {state['messages_dir']}",
        f"generated_at: {state['generated_at']}",
        "",
        "summary:",
    ]
    for key, value in state["summary"].items():
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("current entries:")
    current = [entry for entry in state["entries"] if entry["status"] == "current"]
    if current:
        for entry in current:
            lines.append(
                f"  {entry['task']}/{entry['id']} {entry['from']}->{entry['to']} {entry['kind']} "
                f"(delivery={entry['delivery']['status'] if entry['delivery'] else 'unknown'})"
            )
    else:
        lines.append("  none")
    lines.append("")
    lines.append("cancelled / conflict entries:")
    special = [entry for entry in state["entries"] if entry["status"] != "current"]
    if special:
        for entry in special:
            lines.append(f"  {entry['task']}/{entry['id']} [{entry['status']}] {entry['from']} {entry['kind']}")
    else:
        lines.append("  none")
    lines.append("")
    lines.append("superseded (retained technical body):")
    if state["superseded_history"]:
        for item in state["superseded_history"]:
            lines.append(
                f"  {item['task']}/{item['id']} -> {', '.join(item['superseded_by'])}"
                f"{' [conflict]' if item['conflict'] else ''}"
            )
    else:
        lines.append("  none")
    lines.append("")
    lines.append("conflicts:")
    if state["conflicts"]:
        for item in state["conflicts"]:
            lines.append(f"  {item['kind']}: {item}")
    else:
        lines.append("  none")
    lines.append("")
    lines.append("executable notices (candidates only; authorization unknown):")
    if state["executable_notices"]:
        for notice in state["executable_notices"]:
            lines.append(f"  {notice['task']}/{notice['id']} {notice['from']} {notice['kind']} -> {notice['to']}")
    else:
        lines.append("  none")
    lines.append("")
    lines.append("unconfirmed delivery/hand-off:")
    unconfirmed = [item for item in state["delivery"] if item["status"] == "unconfirmed"]
    if unconfirmed:
        for item in unconfirmed:
            lines.append(f"  {item['task']}/{item['id']}")
    else:
        lines.append("  none")
    lines.append("")
    lines.append("executability: unknown (authorization / budget / pause are Lead-maintained)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collab.py",
        description=(
            "Explicit one-shot local collaboration helpers. No watcher, scheduler, "
            "automatic delivery, automatic role selection or runtime authorization."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish_parser = subparsers.add_parser("publish", help="atomically publish one validated message")
    publish_parser.add_argument("file", type=Path, help="message file to validate and publish")
    publish_parser.add_argument("--task-dir", type=Path, help="task directory; messages go to <task-dir>/messages")
    publish_parser.add_argument("--from", dest="from_role", choices=sorted(ROLES), help="declared sender role")
    publish_parser.set_defaults(handler=_cmd_publish)

    ledger_parser = subparsers.add_parser("ledger", help="local budget pre-check and atomic reservation")
    ledger_sub = ledger_parser.add_subparsers(dest="ledger_command", required=True)

    def ledger_paths(target: argparse.ArgumentParser) -> None:
        target.add_argument("--task-dir", type=Path, default=Path("."), help="task directory (default: .)")
        target.add_argument("--ledger", type=Path, help="explicit ledger JSON path (default: TASK_DIR/budget.json)")

    init_parser = ledger_sub.add_parser("init", help="create a new ledger without overwriting an existing one")
    ledger_paths(init_parser)
    init_parser.add_argument("--baseline", help="JSON object of role quotas, or {quota:..., baseline_ref:...}")
    init_parser.add_argument("--baseline-ref", help="parent scope / user-approved baseline reference")
    init_parser.add_argument("--parent-scope", help="parent budget scope that this ledger inherits")
    init_parser.add_argument("--quota", action="append", default=[], metavar="ROLE=N", help="simple quota entry")
    init_parser.set_defaults(handler=_cmd_ledger)

    check_parser = ledger_sub.add_parser(
        "check",
        help="read-only budget pre-check; exits 2 on unknown or any over-budget role",
    )
    ledger_paths(check_parser)
    check_parser.set_defaults(handler=_cmd_ledger)

    reserve_parser = ledger_sub.add_parser("reserve", help="atomically check and reserve one call")
    ledger_paths(reserve_parser)
    reserve_parser.add_argument("role", choices=sorted(ROLES))
    reserve_parser.add_argument("call_ref")
    reserve_parser.add_argument("--source", default="cli")
    reserve_parser.set_defaults(handler=_cmd_ledger)

    settle_parser = ledger_sub.add_parser("settle", help="mark a reservation started / settled / unknown")
    ledger_paths(settle_parser)
    settle_parser.add_argument("role", choices=sorted(ROLES))
    settle_parser.add_argument("call_ref")
    settle_parser.add_argument("--status", choices=["started", "settled", "unknown"], default="settled")
    settle_parser.add_argument("--source", default="cli")
    settle_parser.set_defaults(handler=_cmd_ledger)

    release_parser = ledger_sub.add_parser("release", help="release only an unstarted reserved entry")
    ledger_paths(release_parser)
    release_parser.add_argument("role", choices=sorted(ROLES))
    release_parser.add_argument("call_ref")
    release_parser.add_argument("--source", default="cli")
    release_parser.set_defaults(handler=_cmd_ledger)

    preserve_parser = subparsers.add_parser("preserve", help="candidate manifests and evidence transcription")
    preserve_sub = preserve_parser.add_subparsers(dest="preserve_command", required=True)

    manifest_parser = preserve_sub.add_parser("manifest", help="build or verify a candidate identity manifest")
    manifest_parser.add_argument("--base", type=Path, help="repository / baseline directory")
    manifest_parser.add_argument("--files", nargs="+", default=[], help="declared delivery files")
    manifest_parser.add_argument("--untracked", nargs="+", default=[], help="declared untracked delivery files")
    manifest_parser.add_argument("--exclude", action="append", default=[], help="additional exclude glob")
    manifest_parser.add_argument("--out", type=Path, help="write the manifest JSON here")
    manifest_parser.add_argument("--sha256", action="store_true", help="add a manifest self-digest")
    manifest_parser.add_argument("--force", action="store_true", help="replace an existing --out manifest")
    manifest_parser.add_argument("--verify", type=Path, help="verify an existing manifest instead of building")
    manifest_parser.set_defaults(handler=_cmd_preserve)

    archive_parser = preserve_sub.add_parser("archive", help="copy an original return plus transcription metadata")
    archive_parser.add_argument("--return-file", type=Path, required=True)
    archive_parser.add_argument("--from", dest="original_author", required=True, choices=sorted(ROLES))
    archive_parser.add_argument("--transcribed-by", required=True, choices=sorted(ROLES))
    archive_parser.add_argument("--call-ref", required=True)
    archive_parser.add_argument("--version", required=True)
    archive_parser.add_argument("--redaction", help="caller-provided redaction note")
    archive_parser.add_argument("--out", type=Path, help="evidence directory (default: .agent/evidence)")
    archive_parser.set_defaults(handler=_cmd_preserve)

    state_parser = subparsers.add_parser("state", help="derive a disposable message-state projection")
    state_parser.add_argument("task_dir", type=Path)
    state_parser.add_argument("--format", choices=["json", "text"], default="json")
    state_parser.set_defaults(handler=_cmd_state)
    return parser


def _cmd_publish(args: argparse.Namespace) -> int:
    result = publish(args.file, task_dir=args.task_dir, from_role=args.from_role)
    _emit_json(result)
    return 0


def _cmd_ledger(args: argparse.Namespace) -> int:
    command = args.ledger_command
    if command == "init":
        result = ledger_init(
            task_dir=args.task_dir,
            baseline=args.baseline,
            quota_items=args.quota,
            baseline_ref=args.baseline_ref,
            parent_scope=args.parent_scope,
            ledger=args.ledger,
        )
    elif command == "check":
        result = ledger_check(task_dir=args.task_dir, ledger=args.ledger)
    elif command == "reserve":
        result = ledger_reserve(
            args.role, args.call_ref, task_dir=args.task_dir, ledger=args.ledger, source=args.source
        )
    elif command == "settle":
        result = ledger_settle(
            args.role,
            args.call_ref,
            status=args.status,
            task_dir=args.task_dir,
            ledger=args.ledger,
            source=args.source,
        )
    elif command == "release":
        result = ledger_release(
            args.role, args.call_ref, task_dir=args.task_dir, ledger=args.ledger, source=args.source
        )
    else:  # pragma: no cover - argparse prevents this
        raise CollabError(f"unknown ledger command: {command}")
    _emit_json(result)
    if command == "check":
        roles = result.get("roles", {})
        failed = result.get("status") == "unknown" or any(
            isinstance(item, dict) and item.get("status") == "over" for item in roles.values()
        )
        return 2 if failed else 0
    return 0


def _cmd_preserve(args: argparse.Namespace) -> int:
    if args.preserve_command == "manifest":
        if args.verify is not None:
            result = verify_manifest(args.verify, base_override=args.base)
            _emit_json(result)
            return 0 if result["status"] in {"ok", "ok-with-unknown-baseline"} else 1
        if args.base is None:
            raise CollabError("manifest requires --base")
        if not args.files and not args.untracked:
            raise CollabError("manifest requires at least one --files or --untracked path")
        result = preserve_manifest(
            args.base,
            files=args.files,
            untracked=args.untracked,
            excludes=args.exclude,
            out=args.out,
            want_sha256=args.sha256,
            force=args.force,
        )
        if args.out is not None:
            _emit_json(
                {
                    "status": "manifest-written",
                    "out": str(Path(args.out)),
                    "files": len(result["files"]),
                    "excluded": len(result["excluded"]),
                    "manifest_sha256": result.get("manifest_sha256"),
                    "note": "Identity manifest only; it does not prove tests ran or coverage is complete.",
                }
            )
        else:
            _emit_json(result)
        return 0
    if args.preserve_command == "archive":
        result = preserve_archive(
            args.return_file,
            original_author=args.original_author,
            transcribed_by=args.transcribed_by,
            call_ref=args.call_ref,
            version=args.version,
            redaction=args.redaction,
            out=args.out,
        )
        _emit_json(result)
        return 0
    raise CollabError(f"unknown preserve command: {args.preserve_command}")


def _cmd_state(args: argparse.Namespace) -> int:
    state = derive_state(args.task_dir)
    if args.format == "text":
        print(_format_state_text(state))
    else:
        _emit_json(state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except CollabError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return error.code
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
