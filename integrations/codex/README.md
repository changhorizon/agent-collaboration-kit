# Codex 适配计划（尚未接线）

> 状态：设计计划稿，2026-10-09。**本目录尚未提供任何已实现、已接线或已验收的 Codex 角色适配**。以下能力来自本机 `codex --help` / `codex exec --help` 的只读核对，未运行跨客户端任务，也未验证事件输出、角色隔离、会话独立或自动路由。任何“计划”都不得被读作已支持。

## 已核实的事实（2026-10-09）

- 本机安装 `codex-cli 0.156.1`（`codex --version`），可执行文件位于 `$HOME/.local/bin/codex`。
- CLI 表面经 `--help` 核对到以下选项（仅证明“列出该选项”，不证明角色隔离或投递已生效）：
  - `codex exec` 非交互运行；`--json` 输出 JSONL 事件；`-C/--cd <DIR>` 指定工作根；`--worktree`、`--add-dir`。
  - `-m/--model`、`-p/--profile`（叠加 `$CODEX_HOME/<name>.config.toml`）、`-c/--config key=value`（覆盖 `~/.codex/config.toml` 的 TOML 项）。
  - `-s/--sandbox`（read-only / workspace-write / danger-full-access）、`--ask-for-approval`（on-request / never）、`--approve-for-me`。
  - `--output-schema`、`--output-last-message`、`--skip-git-repo-check`、`--ignore-rules`（跳过 execpolicy `.rules`）。
  - 会话/服务面：`agents`（未标 experimental）、`app-server`、`remote-control`、`exec-server`（此三者标 experimental）。
- `codex agents` 的“agents”在 `--help` 中列为“agent sessions”（运行中的会话），并不等同于 OpenCode 那种“命名角色 + frontmatter 权限”的角色定义文件；Codex 是否另有命名角色机制，本轮未从已核对的 CLI 入口确认。

## 与 OpenCode 的关键结构差异（待闭合）

1. **“命名角色定义文件”能力未确认**：OpenCode 用 `mode/frontmatter 权限` 的角色文件。本轮证据仅 `codex --help` / `codex exec --help`，**未从已核对的 CLI 入口确认 Codex 有等价物，待专项核实**；若确认无等价物，角色须转译为 **config profile（TOML）+ execpolicy `.rules` + 注入角色内容**，不能照搬 `integrations/opencode/agents/*.md`。
2. **子代理委派能力未确认**：Coder / Validator / Reviewer 在 OpenCode 由 Lead 经 `task` 子代理工具调用。本轮未从已核对的 CLI 入口确认 Codex 是否有等价的受控子任务委派（嵌套 `codex exec`、插件或 execpolicy 机制），**待专项核实**；未确认前只能标为 Lead 二次调用 `codex exec` 的人工交接，不能冒充子代理拓扑。
3. **独立会话与信箱交接**：Advisor / Auditor 的“真正独立持久会话 + 用户转发交接通知”依赖 Codex 的会话管理（`resume` / `fork` / `queue` / `app-server`）。这些接口存在不等于已满足 cwd 一致、角色隔离、无父子上下文继承；**未验证**。
4. **取时与只读信箱写入**：独立角色须能安全读取精确 UTC（`date -u`）并在共享信箱仅写本人署名消息；Codex 侧需按角色配置 sandbox/approval 与 execpolicy，且逐角色实测，不因文档要求就放宽通用命令权限。

## 拟议映射（计划，未实现）

- **通用权威复用**：角色职责/权限/触发/授权仍只来自 `.agent/collaboration.md`，操作内容只来自 `.agent/prompts/<role>.md`；Codex 适配只负责加载格式、模型、sandbox、approval 与启动，**不另立角色规则**。
- **每角色 → 一个命名 config profile**（`$CODEX_HOME/<role>.config.toml`），按角色叠加 model + sandbox + approval + execpolicy；启动时以 `-p <role>` 选择。
- **角色内容注入**：会话指令指向消费方安装的 `.agents/agent-collaboration-kit/prompts/<role>.md` 与 `collaboration.md`（与 OpenCode 相同的指针方式），而不是把职责写进 Codex 配置。
- **子代理**：先核实 Codex 受控委派能力再定；未核实前 Coder / Validator / Reviewer 不宣称已支持，仅标“Lead 人工二次调用”。
- **一致性检查**：参照 `scripts/check_opencode_agents.py`，后续为 Codex profile/规则提供只读漂移检查；本阶段不实现。

## 明确不主张

- 本阶段**未**实现 Codex 适配，未接线任何角色、会话或投递，未运行跨客户端任务。
- 不把某个模型平台的自定义提示词或 `~/.codex/config.toml` 升格为协作权威。
- ChatGPT 桌面版、终端等入口能否自动读取项目规则、访问文件或启动角色须另行核实，本计划不含，也不预设其已支持。
- 跨客户端交接仍以共享消息/证据语义为准；Codex 的可用通知/会话接口须单独验证，不能为宣称通用而假造自动投递。

## 后续（另设阶段、另取授权）

1. 核实 Codex 子代理委派与独立会话隔离；记录正反例原件。
2. 产出七角色（含 Ally）profile + execpolicy 模板与只读一致性检查器。
3. 在无生产副作用的隔离项目跑权限负例（越权命令是否被 sandbox/approval 真正拒绝）。
4. 逐项验证 cwd 一致、UTC 取时、信箱只写本人、断线补偿；任一未过即标部分可用。
