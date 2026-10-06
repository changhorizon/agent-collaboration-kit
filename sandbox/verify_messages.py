#!/usr/bin/env python3
"""Check message structure and references, never runtime permissions or factual truth."""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

FIELDS = {
    "id", "task", "from", "to", "kind", "created_at", "cwd",
    "object_ref", "version_ref", "reply_to", "supersedes",
}
ROLES = {"lead", "coder", "validator", "reviewer", "auditor", "advisor"}
KINDS = {"request", "received", "result", "advice", "review"}
VERDICTS = {"PASS", "PASS WITH WARNINGS", "FAIL", "ESCALATE"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


@dataclass(frozen=True)
class Message:
    path: Path
    header: dict[str, str]
    body: str
    created_at: datetime

    @property
    def key(self) -> tuple[str, str]:
        return self.header["task"], self.header["id"]


def section(body: str, name: str) -> str | None:
    match = re.search(rf"^## {re.escape(name)}(?:（[^\n]*）)?\s*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else None


def parse(path: Path) -> Message:
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError("symlink or oversized message")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening header delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("missing closing header delimiter") from error
    header = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise ValueError("invalid header line")
        name, value = line.split(":", 1)
        if name in header:
            raise ValueError(f"duplicate field: {name}")
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid quoted scalar: {name}") from error
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        header[name] = value
    if set(header) != FIELDS:
        raise ValueError(f"header fields missing={sorted(FIELDS - set(header))} extra={sorted(set(header) - FIELDS)}")
    for name in ("id", "task"):
        if not IDENTIFIER.fullmatch(header[name]):
            raise ValueError(f"invalid {name}")
    for name in ("reply_to", "supersedes"):
        if header[name] != "null" and not IDENTIFIER.fullmatch(header[name]):
            raise ValueError(f"invalid {name}")
    if header["from"] not in ROLES or header["to"] not in ROLES | {"user"}:
        raise ValueError("invalid role")
    if header["kind"] not in KINDS:
        raise ValueError("invalid kind")
    if header["from"] in {"coder", "validator", "reviewer"} and header["to"] != "lead":
        raise ValueError("subagent output must be addressed to Lead")
    if not Path(header["cwd"]).is_absolute():
        raise ValueError("cwd must be absolute")
    if not header["object_ref"] or not header["version_ref"]:
        raise ValueError("object_ref and version_ref are required (use unknown if necessary)")
    if not header["created_at"].endswith(("Z", "+00:00")):
        raise ValueError("created_at must be UTC ISO-8601")
    try:
        created_at = datetime.fromisoformat(header["created_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid created_at") from error
    body = "\n".join(lines[end + 1:]).strip()
    if not body:
        raise ValueError("missing message body")
    kind, sender = header["kind"], header["from"]
    if kind == "request":
        if sender not in {"lead", "advisor"}:
            raise ValueError("only Lead or Advisor may issue a file request")
        status = section(body, "指令状态")
        if status not in {"active", "cancelled"}:
            raise ValueError("request requires ## 指令状态: active or cancelled")
    if kind == "advice" and sender != "advisor":
        raise ValueError("only Advisor may issue advice")
    if kind == "review" and sender not in {"validator", "reviewer", "auditor"}:
        raise ValueError("review must come from Validator, Reviewer or Auditor")
    if kind == "review":
        verdict = section(body, "判定")
        if verdict not in VERDICTS:
            raise ValueError("review requires a supported ## 判定")
        if verdict.startswith("PASS") and (header["object_ref"] == "unknown" or header["version_ref"] == "unknown"):
            raise ValueError("PASS needs a known object_ref and version_ref")
        if sender == "auditor" and header["to"] != "user":
            raise ValueError("Auditor original review must be addressed to user")
    return Message(path, header, body, created_at)


def validate(root: Path) -> tuple[int, int, list[str]]:
    if root.is_symlink() or not root.is_dir():
        return 0, 0, [f"{root}: message directory not found"]
    messages: dict[tuple[str, str], Message] = {}
    errors = []
    for path in sorted(root.rglob("*.md")):
        try:
            message = parse(path)
            if message.key in messages:
                raise ValueError(f"duplicate message ID within task: {message.key}")
            messages[message.key] = message
        except (OSError, UnicodeError, ValueError) as error:
            errors.append(f"{path}: {error}")
    if not messages and not errors:
        errors.append(f"{root}: no messages")

    edges: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for key, message in messages.items():
        edges[key] = set()
        for field in ("reply_to", "supersedes"):
            value = message.header[field]
            if value == "null":
                continue
            target = (key[0], value)
            parent = messages.get(target)
            if parent is None:
                errors.append(f"{message.path}: {field} target {value} missing from task {key[0]}")
                continue
            edges[key].add(target)
            if message.created_at < parent.created_at:
                errors.append(f"{message.path}: {field} points to a later timestamp")
            if field == "supersedes" and (
                message.header["kind"] != parent.header["kind"]
                or message.header["from"] != parent.header["from"]
            ):
                errors.append(f"{message.path}: supersedes must keep kind and author")

    seen, visiting = set(), set()

    def visit(key: tuple[str, str]) -> None:
        if key in visiting:
            errors.append(f"{key}: reference cycle")
            return
        if key in seen:
            return
        visiting.add(key)
        for parent in edges[key]:
            visit(parent)
        visiting.remove(key)
        seen.add(key)

    for key in edges:
        visit(key)
    return len(messages), len({task for task, _ in messages}), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("messages", type=Path, help="directory containing per-task Markdown messages")
    args = parser.parse_args()
    count, tasks, errors = validate(args.messages)
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        print("Runtime permissions, delivery and factual truth NOT VERIFIED.")
        return 1
    print(f"PASS: {count} structurally valid messages in {tasks} task(s).")
    print("Runtime permissions, delivery and factual truth NOT VERIFIED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
