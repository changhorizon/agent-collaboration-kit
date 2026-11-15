#!/usr/bin/env python3
"""Install or upgrade a self-contained collaboration protocol into a consumer directory."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / ".agent"
# Blank static templates for the state files. They are kept separate from the
# live .agent/ runtime state so that locally filled project state never leaks
# into consumer installations.
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
STATE_FILES = (
    "decision-log.md",
    "project-state.md",
    "risk-register.md",
)
RELATIVE_DEST = Path(".agents/agent-collaboration-kit")
FILES = (
    "collaboration.md",
    "decision-log.md",
    "evidence/README.md",
    "exchange/README.md",
    "exchange/message-template.md",
    "milestones/README.md",
    "project-state.md",
    "risk-register.md",
    "prompts/advisor.md",
    "prompts/ally.md",
    "prompts/auditor.md",
    "prompts/coder.md",
    "prompts/lead.md",
    "prompts/reviewer.md",
    "prompts/validator.md",
)
# Generated metadata, not a package source file. It still belongs to the
# authoritative install/overwrite manifest so upgrades can identify the
# installed revision and never treat the stamp as a hidden side channel.
VERSION_FILE = ".kit-version.json"
MANIFEST = FILES + (VERSION_FILE,)
BACKUP_PREFIX = "agent-collaboration-kit.backup-"
ENTRY = """## Agent Collaboration Kit（可选）

仅当本项目实际以 Lead 为主会话运行时（启用可选入口 Ally 时经 Ally），使用本项目安装的
`.agents/agent-collaboration-kit/collaboration.md`；消息语法见本项目
`.agents/agent-collaboration-kit/exchange/README.md`。本地完整协议优先，上级协作
协议不叠加；项目原有业务规则及上级工作空间的文件权限、Git 规则继续生效。
文档安装不代表角色权限和通知已接线或验收，也不自动启用 Ally。
"""


class UpgradeError(ValueError):
    """Upgrade failure that may carry a retained backup location."""

    def __init__(self, message: str, backup_dir: Path | None = None):
        super().__init__(message)
        self.backup_dir = backup_dir


def package_source(relative: str) -> Path:
    """Return the static source for a packaged relative path.

    State files come from the blank templates, never from the live .agent/
    runtime state in this repository.
    """
    if relative in STATE_FILES:
        return TEMPLATES / relative
    return SOURCE / relative


def _validate_package_sources() -> None:
    """Require every package source to be a regular non-symlink file."""
    for relative in FILES:
        source = package_source(relative)
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing or linked package source: {relative}")


def _run_git(arguments: list[str], cwd: Path) -> str | None:
    """Run a read-only git command without a shell, returning stdout or None."""
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def compute_source_version(root: Path | None = None) -> dict:
    """Return the kit source revision.

    Dirty detection uses ``git status --porcelain`` in its default mode, so
    both modified tracked files and untracked files count as dirty. If git is
    unavailable the commit is reported as ``unknown`` and dirty as ``None``.
    """
    root = (root or SOURCE.parent).resolve()
    commit = _run_git(["rev-parse", "HEAD"], root)
    if commit is None or not commit.strip():
        return {"source_commit": "unknown", "source_dirty": None}
    status = _run_git(["status", "--porcelain"], root)
    return {
        "source_commit": commit.strip(),
        "source_dirty": None if status is None else bool(status.strip()),
    }


def _target_version() -> dict:
    version = compute_source_version()
    version["installed_at"] = datetime.now(timezone.utc).isoformat()
    return version


def read_installed_version(destination: Path) -> dict | None:
    """Read the installed version stamp, or return None if it is unusable."""
    version_file = destination / VERSION_FILE
    if version_file.is_symlink() or not version_file.is_file():
        return None
    try:
        data = json.loads(version_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("source_commit"):
        return None
    return data


def _format_version(version: dict) -> str:
    commit = version.get("source_commit") or "unknown"
    dirty = version.get("source_dirty")
    if dirty is None:
        state = "unknown"
    elif dirty:
        state = "dirty"
    else:
        state = "clean"
    text = f"{commit} ({state})"
    installed_at = version.get("installed_at")
    if installed_at:
        text += f" installed_at={installed_at}"
    return text


def _same_bytes(first: Path, second: Path) -> bool:
    try:
        return first.read_bytes() == second.read_bytes()
    except OSError:
        return False


def classify_upgrade(destination: Path) -> dict[str, list[str]]:
    """Classify packaged paths against an existing installation.

    State files are ``preserve`` only when the installed path is a regular
    non-symlink file, and ``restore`` when it is missing. Any other state path
    (symlink, directory, or special file) is rejected: upgrade must never
    silently replace or delete non-regular state data. Static files are
    ``add`` when absent, ``unchanged`` when byte-identical to
    ``package_source``, and ``changed`` when an installed copy differs. A
    symlink or non-file at a static path is treated as ``changed`` so it is
    visible rather than silently followed.
    """
    categories: dict[str, list[str]] = {
        "add": [],
        "unchanged": [],
        "changed": [],
        "restore": [],
        "preserve": [],
    }
    for relative in FILES:
        installed = destination / relative
        if relative in STATE_FILES:
            if installed.is_symlink():
                raise ValueError(
                    f"state file {relative} is not a regular file; refusing to replace or delete it "
                    f"(状态文件 {relative} 非普通文件，拒绝替换/删除)"
                )
            if not installed.exists():
                categories["restore"].append(relative)
            elif not installed.is_file():
                raise ValueError(
                    f"state file {relative} is not a regular file; refusing to replace or delete it "
                    f"(状态文件 {relative} 非普通文件，拒绝替换/删除)"
                )
            else:
                categories["preserve"].append(relative)
            continue
        if installed.is_symlink():
            categories["changed"].append(relative)
        elif not installed.exists():
            categories["add"].append(relative)
        elif not installed.is_file():
            categories["changed"].append(relative)
        elif _same_bytes(installed, package_source(relative)):
            categories["unchanged"].append(relative)
        else:
            categories["changed"].append(relative)
    return categories


def _prepare_consumer(target: Path, *, for_upgrade: bool):
    if not target.is_dir() or target.is_symlink():
        raise ValueError("target must be an existing, non-symlink directory")
    target = target.resolve()
    agents = target / ".agents"
    if agents.is_symlink():
        raise ValueError("refusing to follow a .agents symlink")
    if agents.exists() and not agents.is_dir():
        raise ValueError(".agents exists and is not a directory")
    destination = target / RELATIVE_DEST
    if (
        not for_upgrade
        and (target / ".agent/collaboration.md").is_file()
        and (target / ".agent/exchange/README.md").is_file()
    ):
        raise ValueError("project already has a complete local protocol; do not replace it automatically")
    agents_file = target / "AGENTS.md"
    if agents_file.is_symlink():
        raise ValueError("refusing to edit an AGENTS.md symlink")
    if agents_file.is_dir():
        raise ValueError("AGENTS.md is a directory; merge the local pointer manually")
    existing = agents_file.read_text(encoding="utf-8") if agents_file.exists() else ""
    refs = re.findall(r"`([^`]+(?:collaboration\.md|exchange/README\.md))`", existing)
    if any(Path(ref).is_absolute() or ".." in Path(ref).parts for ref in refs):
        raise ValueError("AGENTS.md references a protocol outside its own directory scope")
    pointer = str(RELATIVE_DEST / "collaboration.md")
    if "agent-collaboration-kit" in existing and pointer not in existing:
        raise ValueError("AGENTS.md mentions this kit without a local installation pointer; merge manually")
    return target, agents, destination, agents_file, existing, pointer not in existing


def _append_entry(agents_file: Path, existing: str) -> None:
    if existing:
        with agents_file.open("a", encoding="utf-8") as output:
            output.write(("\n" if existing.endswith("\n") else "\n\n") + ENTRY)
    else:
        agents_file.write_text(ENTRY, encoding="utf-8")


def _populate_staging(
    staging: Path, version: dict, state_sources: dict[str, Path] | None = None
) -> None:
    for relative in FILES:
        output = staging / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if relative in STATE_FILES and state_sources is not None:
            source = state_sources[relative]
        else:
            source = package_source(relative)
        shutil.copy2(source, output)
    version_path = staging / VERSION_FILE
    version_path.write_text(
        json.dumps(version, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _resolve_backup_dir(
    target: Path,
    agents: Path,
    destination: Path,
    backup_dir: Path | None,
    now: datetime,
) -> Path:
    if backup_dir is None:
        candidate = agents / (BACKUP_PREFIX + now.strftime("%Y%m%dT%H%M%S%fZ"))
    else:
        candidate = Path(backup_dir)
        if not candidate.is_absolute():
            candidate = target / candidate
    candidate = candidate.resolve()
    agents_resolved = agents.resolve()
    try:
        candidate.relative_to(agents_resolved)
    except ValueError:
        raise ValueError("backup directory must be inside the target .agents/ directory") from None
    if candidate == agents_resolved:
        raise ValueError("backup directory must be a subdirectory of .agents/")
    destination_resolved = destination.resolve()
    if candidate == destination_resolved or destination_resolved in candidate.parents:
        raise ValueError("backup directory must not be inside the installed kit directory")
    return candidate


def _validate_backup_destination(backup_dir: Path) -> None:
    if not backup_dir.exists() and not backup_dir.is_symlink():
        return
    if backup_dir.is_symlink() or not backup_dir.is_dir():
        raise ValueError(f"backup path exists and is not a directory: {backup_dir}")
    if any(backup_dir.iterdir()):
        raise ValueError(f"backup directory already exists and is not empty: {backup_dir}")


def _backup_conflicts(destination: Path, backup_dir: Path, relatives: list[str]) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for relative in relatives:
        output = backup_dir / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination / relative, output)


def _upgrade_report(
    destination: Path,
    installed_version: dict,
    target_version: dict,
    categories: dict[str, list[str]],
    backup_dir: Path,
    backup_files: list[str],
) -> list[str]:
    lines = [
        f"installed version: {_format_version(installed_version)}",
        f"target version: {_format_version(target_version)}",
    ]
    for name in ("add", "unchanged", "changed", "restore", "preserve"):
        files = categories[name]
        if name == "restore" and files:
            detail = ", ".join(
                f"{relative} (状态文件缺失，将从空白模板安装)" for relative in files
            )
        else:
            detail = ", ".join(files) if files else "(none)"
        lines.append(f"manifest {name}: {detail}")
    conflicts = categories["changed"]
    lines.append(f"conflicts: {', '.join(conflicts) if conflicts else '(none)'}")
    lines.append(f"version file: {destination / VERSION_FILE}")
    lines.append(f"backup dir: {backup_dir}")
    lines.append(f"backup files: {', '.join(backup_files) if backup_files else '(none)'}")
    lines.append(
        "rollback scope: only backed-up changed static files are covered; "
        "STATE_FILES are not backed up and are not overwritten; "
        "consumer .agent/ runtime data is out of scope for this operation."
    )
    lines.append(
        "回退范围：仅覆盖已备份的冲突静态文件；STATE_FILES 不备份、不被覆盖；"
        "`.agent/` 运行数据不在本次操作范围。"
    )
    lines.append(
        f"rollback: copy the backup directory contents back into {destination} "
        "to restore the previous conflict files."
    )
    return lines


def install(target: Path, dry_run: bool = False) -> list[str]:
    """Perform the first-time installation of the kit into a consumer project."""
    target, agents, destination, agents_file, existing, add_entry = _prepare_consumer(
        target, for_upgrade=False
    )
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"existing installation: {destination}; use --upgrade to migrate")
    _validate_package_sources()

    version = _target_version()
    planned = [f"{destination / relative}" for relative in MANIFEST]
    if add_entry:
        planned.append(f"append local pointer to {agents_file}")
    if dry_run:
        return planned

    agents.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".collab-install-", dir=agents))
    try:
        _populate_staging(staging, version)
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if add_entry:
        try:
            _append_entry(agents_file, existing)
        except OSError:
            shutil.rmtree(destination)
            raise
    return planned


def upgrade(
    target: Path,
    dry_run: bool = False,
    force: bool = False,
    backup_dir: Path | None = None,
) -> list[str]:
    """Upgrade an existing installation, preserving state files and runtime data.

    Returns a report of the installed/target versions, the coverage manifest,
    conflicts, the version file to write, and the backup/rollback plan.
    """
    target, agents, destination, agents_file, existing, add_entry = _prepare_consumer(
        target, for_upgrade=True
    )
    if not destination.exists() and not destination.is_symlink():
        raise ValueError("no existing installation; run first-time install without --upgrade")
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("existing installation is not a normal directory; refusing to upgrade")
    installed_version = read_installed_version(destination)
    if installed_version is None:
        raise ValueError(
            f"installed version unknown: {destination / VERSION_FILE} is missing or unreadable"
        )

    _validate_package_sources()
    target_version = _target_version()
    categories = classify_upgrade(destination)
    conflicts = categories["changed"]
    state_sources: dict[str, Path] = {}
    for relative in STATE_FILES:
        if relative in categories["preserve"]:
            state_sources[relative] = destination / relative
        else:
            state_sources[relative] = package_source(relative)
    now = datetime.now(timezone.utc)
    resolved_backup = _resolve_backup_dir(target, agents, destination, backup_dir, now)
    report = _upgrade_report(
        destination,
        installed_version,
        target_version,
        categories,
        resolved_backup,
        conflicts,
    )
    if dry_run:
        _validate_backup_destination(resolved_backup)
        return report
    if conflicts and not force:
        raise ValueError(
            "upgrade conflicts in customized files: "
            + ", ".join(conflicts)
            + "; review the differences and rerun with --force or merge manually"
        )
    _validate_backup_destination(resolved_backup)

    staging = Path(tempfile.mkdtemp(prefix=".collab-upgrade-", dir=agents))
    old = staging.with_name(staging.name + ".old")
    moved_old = False
    backup_started = False
    try:
        _populate_staging(staging, target_version, state_sources)
        if conflicts:
            backup_started = True
            _backup_conflicts(destination, resolved_backup, conflicts)
        destination.rename(old)
        moved_old = True
        try:
            staging.rename(destination)
        except OSError:
            old.rename(destination)
            moved_old = False
            raise
        try:
            if add_entry:
                _append_entry(agents_file, existing)
        except OSError:
            shutil.rmtree(destination, ignore_errors=True)
            old.rename(destination)
            moved_old = False
            raise
        shutil.rmtree(old, ignore_errors=True)
        moved_old = False
    except (OSError, ValueError) as error:
        if backup_started:
            raise UpgradeError(
                f"{error}; backups retained at {resolved_backup}",
                resolved_backup,
            ) from error
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if moved_old and old.exists():
            if not destination.exists():
                old.rename(destination)
            else:
                shutil.rmtree(old, ignore_errors=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True, help="existing workspace or project root")
    parser.add_argument("--dry-run", action="store_true", help="report planned changes without writing")
    parser.add_argument("--upgrade", action="store_true", help="upgrade an existing installation")
    parser.add_argument("--force", action="store_true", help="overwrite customized static files on upgrade")
    parser.add_argument("--backup-dir", type=Path, help="backup directory inside the target .agents/")
    args = parser.parse_args()
    if args.force and not args.upgrade:
        parser.error("--force requires --upgrade")
    if args.backup_dir is not None and not args.upgrade:
        parser.error("--backup-dir requires --upgrade")
    try:
        if args.upgrade:
            report = upgrade(
                args.target,
                dry_run=args.dry_run,
                force=args.force,
                backup_dir=args.backup_dir,
            )
        else:
            planned = install(args.target, dry_run=args.dry_run)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    if args.upgrade:
        print("UPGRADE PLAN" if args.dry_run else "UPGRADED")
        for line in report:
            print(line)
        if not args.dry_run:
            print("Backups are retained for manual rollback of changed static files only.")
    else:
        print("PLAN" if args.dry_run else "INSTALLED")
        for item in planned:
            print(item)
    print("Runtime roles, permissions and delivery still require separate project acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
