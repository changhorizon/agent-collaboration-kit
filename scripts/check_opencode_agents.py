#!/usr/bin/env python3
"""Compare six versioned OpenCode agent definitions with an explicit directory."""

import argparse
from pathlib import Path


ROLES = ("lead", "coder", "validator", "reviewer", "advisor", "auditor")
SNAPSHOT = Path(__file__).resolve().parents[1] / "integrations" / "opencode" / "agents"


def check(installed_dir: Path) -> tuple[list[str], bool]:
    if installed_dir.is_symlink() or not installed_dir.is_dir():
        return [f"FAIL: target is not a regular directory: {installed_dir}"], False

    results = []
    matched = True
    for role in ROLES:
        name = f"{role}.md"
        source = SNAPSHOT / name
        installed = installed_dir / name
        if source.is_symlink() or not source.is_file():
            results.append(f"FAIL: invalid snapshot: {name}")
            matched = False
            continue
        if installed.is_symlink() or not installed.is_file():
            results.append(f"FAIL: missing or linked installed file: {name}")
            matched = False
            continue
        try:
            same = source.read_bytes() == installed.read_bytes()
        except OSError as error:
            results.append(f"FAIL: cannot compare {name}: {error.strerror}")
            matched = False
            continue
        results.append(f"{'MATCH' if same else 'DRIFT'}: {name}")
        matched &= same
    results.append(f"{'PASS' if matched else 'FAIL'}: {len(ROLES)} OpenCode agent definitions checked")
    return results, matched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-dir", type=Path, required=True, help="directory containing the active agent files")
    args = parser.parse_args()
    results, matched = check(args.installed_dir)
    for line in results:
        print(line)
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
