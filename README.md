# Agent Collaboration Kit

面向长期软件项目的多 Agent 协作规范与项目模板。它区分实现、验收、变更审阅、系统审阅和重大技术裁决，并要求关键结论能回到原始证据。当前是候选规范，以 OpenCode 为主要运行环境；**本仓库不自动配置角色、权限、消息通知或生产操作**。

- [完整协作规范](.agent/collaboration.md)：唯一的角色、触发条件与授权规则来源。
- [统一消息协议](.agent/exchange/README.md)：独立会话信箱与子代理返回的消息语义。
- [沙盒验证](sandbox/README.md)：可复用协议检查、虚构用例与项目接入冒烟说明。

版本通过 Git 提交和标签追溯；工作树只保留现行规范，不按版本复制多份文件。

## 角色与工作流

Lead 是用户的日常入口；Coder、Validator、Reviewer 是任务限定的子代理。Advisor 独立处理重大技术取舍；Auditor 在阶段或系统性问题触发时独立审阅，常规原始报告回 Lead，用户可按需直接核对。两个独立角色与 Lead 均通过共享信箱交接，用户负责在无自动通知机制时转发正式消息。六个角色不代表六个常驻窗口或六种必须使用的模型。

普通任务由 Lead 定义范围、调度实现、组织检查并交付；只有命中规范中的条件才增加变更级 Reviewer、系统级 Auditor 或 Advisor 裁决。技术建议、独立验收、用户风险接受与执行授权不能互相替代。完整权限与流程以协作规范为准，此处不重复维护。

## 接入项目

1. 先核对目标项目现行的 `AGENTS.md`、权限与 Git 工作流。实际启用 Lead 的项目若没有本地完整协议，按 `AGENTS.md` 继承规则使用最近的上级已安装副本；**不必每个项目重复安装**。若项目安装自己的完整协议，只选该项目副本，上级副本的协作规则不叠加。
2. 仅当工作空间首次需要自己的安装副本，或项目需要独立于上层的本地覆盖时，从本仓库运行 `python3 scripts/install.py --target "/path/to/consumer" --dry-run` 预览，再去掉 `--dry-run` 安装。脚本只复制已列出的静态协议与角色模板到**消费方** `.agents/agent-collaboration-kit/`，并在消费方 `AGENTS.md` 追加本地入口；不会覆盖已有安装、项目状态或源协议。工作空间安装需遵守该工作空间对全局配置文件的授权规则。
3. 在目标项目的运行时配置角色、工具权限、共同工作目录和共享信箱路径；实际写信箱消息的角色须实测能安全读取精确 UTC 时间，不为取时放开通用 Bash。`.agents/` 保存安装的静态规则和空白状态模板；真实项目状态与运行消息应由该项目在 `.agent/` 管理，不把安装模板当作当前事实，也不覆盖既有状态。安装提示词本身不授予工具权限。
4. 独立会话的发信方在写入信箱后按消息协议输出可直接复制的交接通知，由用户原样转发给收件角色；消息写入不等于已送达，`received` 也不代表完成。自动通知属于独立的运行时接入工作，不能直接沿用用户转发 Auditor 请求时的授权语义。
5. 用 `sandbox/` 的无生产副作用用例先检查协议，再在目标项目的隔离范围内做一次针对真实角色和工具权限的最小冒烟。Kit 内检查通过不能替代目标项目的验收。

需要保存的决策与证据应脱敏归档；消费方 `.agent/exchange/tasks/` 是运行消息目录，安装流程不会替其修改 `.gitignore`，需按目标项目的 Git 策略单独排除。

## 本地沙盒检查

需要 Python 3.10+；以下命令只针对仓库内的虚构样例和一次性测试副本：

```bash
python3 -B sandbox/verify_messages.py sandbox/fixtures/messages
python3 -B -m unittest discover -s sandbox/tests -v
```

检查器只判定已实现的结构规则，**不证明**消息作者身份、事实正确性、自动送达或工具权限已生效。消费项目的权限负例必须由相应角色实际调用工具，并保留工具返回；详情见[沙盒说明](sandbox/README.md)。

仓库 CI 在推送到 `main` 时直接触发，以 Python 3.10 和 3.12 运行上述两项检查。CI 只验证 Kit 的协议样例与沙盒测试，不代替消费项目的运行时验收。

## 目录

```text
AGENTS.md                    本仓库维护入口（不复制给消费方）
.agent/                      安装用静态协议源
  collaboration.md           唯一完整协作规范（含触发规则）
  project-state.md           长期状态索引
  decision-log.md            决策记录
  risk-register.md           风险登记
  evidence/README.md         证据索引约定
  milestones/README.md       阶段验收约定
  exchange/README.md         唯一消息协议定义
  exchange/message-template.md  消息填写模板
  exchange/tasks/            首次使用时创建的运行消息目录；自行配置忽略与权限
  prompts/                   可选的角色差异提示词
sandbox/                   可复用协议样例、检查器与项目接入冒烟用例
scripts/install.py         将静态协议安装到消费方 .agents/ 并更新其 AGENTS.md
```

## 状态与许可

本套件尚未证明对所有项目有效；需用真实任务观察有效发现、误报、返工、用户介入次数和总耗时。文档规则与已配置、已实测的运行时限制应分别标注。

许可：[MIT](LICENSE)。
