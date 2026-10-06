#!/usr/bin/env python3
"""Install a self-contained collaboration protocol into a consumer directory."""

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / ".agent"
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
    "prompts/auditor.md",
    "prompts/coder.md",
    "prompts/lead.md",
    "prompts/reviewer.md",
    "prompts/validator.md",
)
ENTRY = """## Agent Collaboration Kit（可选）

仅当本项目实际以 Lead 为主会话/用户入口角色运行时，使用本项目安装的
`.agents/agent-collaboration-kit/collaboration.md`；消息语法见本项目
`.agents/agent-collaboration-kit/exchange/README.md`。本地完整协议优先，上级协作
协议不叠加；项目原有业务规则及上级工作空间的文件权限、Git 规则继续生效。
文档安装不代表角色权限和通知已接线或验收。
"""


def install(target: Path, dry_run: bool = False) -> list[str]:
    if not target.is_dir() or target.is_symlink():
        raise ValueError("target must be an existing, non-symlink directory")
    target = target.resolve()
    agents = target / ".agents"
    if agents.is_symlink():
        raise ValueError("refusing to follow a .agents symlink")
    destination = target / RELATIVE_DEST
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"existing installation: {destination}; refusing to overwrite")
    if (target / ".agent/collaboration.md").is_file() and (target / ".agent/exchange/README.md").is_file():
        raise ValueError("project already has a complete local protocol; do not replace it automatically")
    agents_file = target / "AGENTS.md"
    if agents_file.is_symlink():
        raise ValueError("refusing to edit an AGENTS.md symlink")
    existing = agents_file.read_text(encoding="utf-8") if agents_file.exists() else ""
    refs = re.findall(r"`([^`]+(?:collaboration\.md|exchange/README\.md))`", existing)
    if any(Path(ref).is_absolute() or ".." in Path(ref).parts for ref in refs):
        raise ValueError("AGENTS.md references a protocol outside its own directory scope")
    pointer = str(RELATIVE_DEST / "collaboration.md")
    if "agent-collaboration-kit" in existing and pointer not in existing:
        raise ValueError("AGENTS.md mentions this kit without a local installation pointer; merge manually")
    add_entry = pointer not in existing
    for relative in FILES:
        source = SOURCE / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing or linked package source: {relative}")
    planned = [f"{destination / relative}" for relative in FILES]
    if add_entry:
        planned.append(f"append local pointer to {agents_file}")
    if dry_run:
        return planned

    agents.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".collab-install-", dir=agents) as staging_name:
        staging = Path(staging_name)
        for relative in FILES:
            output = staging / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, output)
        staging.rename(destination)

    if add_entry:
        try:
            if existing:
                with agents_file.open("a", encoding="utf-8") as output:
                    output.write(("\n" if existing.endswith("\n") else "\n\n") + ENTRY)
            else:
                agents_file.write_text(ENTRY, encoding="utf-8")
        except OSError:
            shutil.rmtree(destination)
            raise
    return planned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True, help="existing workspace or project root")
    parser.add_argument("--dry-run", action="store_true", help="report planned changes without writing")
    args = parser.parse_args()
    try:
        planned = install(args.target, dry_run=args.dry_run)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PLAN" if args.dry_run else "INSTALLED")
    for item in planned:
        print(item)
    print("Runtime roles, permissions and delivery still require separate project acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
