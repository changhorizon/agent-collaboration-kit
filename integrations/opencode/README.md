# OpenCode 角色定义基线

`agents/` 保存 2026-10-09 经本轮“角色正文去重”修改后的 OpenCode 1.18.35 六份**适配基线**，含模型、权限 frontmatter 和一段只做“选协议 + 读 `prompts/<role>.md`”的薄加载正文，供核对文件漂移及需要时手动复制安装；不包含凭据。它是本仓库要核对/手动部署的基线，**尚未同步到本机 `~/.config/opencode/agents/` 运行配置**——后者在本基线变更后会出现预期 DRIFT，直到用户按本文件手动重新复制并重启 OpenCode。

这些副本是 OpenCode 的**派生适配，不是协作权威**：角色职责、权限矩阵、拓扑、触发与授权以 `.agent/collaboration.md` 为准，每个角色的操作内容以 `.agent/prompts/<role>.md` 为准。适配正文刻意不重复角色职责，只声明 OpenCode 运行该角色所需的模型、权限与启动方式；模型名与权限 frontmatter 属于本适配层，不属于通用权威。这些副本不是运行时直接引用的配置，也不由 `scripts/install.py` 复制到消费项目。

在 Kit 仓库根目录检查本机定义是否与基线逐字节一致：

```bash
python3 -B scripts/check_opencode_agents.py --installed-dir "$HOME/.config/opencode/agents"
```

检查器仅读取并比较 `lead.md`、`coder.md`、`validator.md`、`reviewer.md`、`advisor.md`、`auditor.md`，不会复制、改写或读取其他角色文件。报告文件名和匹配状态，不打印角色内容；有缺失、符号链接或差异时退出非零。

需要手动安装时，先确认目标机器的模型提供商、OpenCode 版本、项目权限与已有角色定义，备份目标文件，再从 `agents/` **显式复制所需文件**到该机器的 `~/.config/opencode/agents/`。不要把原样副本当作所有机器的默认安全权限；复制后须重启 OpenCode，并以 `opencode debug agent <角色>` 和实际角色工具调用核对加载结果。

若确实要安装全部六份，完成上述核对与备份后可在 Kit 仓库根目录执行（`cp -i` 遇已有文件会先询问，不自动覆盖）：

```bash
mkdir -p "$HOME/.config/opencode/agents"
cp -i integrations/opencode/agents/{lead,coder,validator,reviewer,advisor,auditor}.md "$HOME/.config/opencode/agents/"
```

**边界**：逐字节一致只证明这些定义文件未漂移；不证明 `opencode.jsonc`、项目级角色配置、插件或运行时权限合并结果一致，也不证明 Kit 协议已安装、当前会话已重新加载配置或工具权限已获运行验收。角色文件变更后按实际差异审查，再有意更新本基线和 Git 历史，不静默覆盖运行配置。
