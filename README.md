# Agent Collaboration Kit

面向长期软件项目的多 Agent 协作规范与项目模板。它区分实现、验收、变更审阅、系统审阅和重大技术裁决，并要求关键结论能回到原始证据。当前是候选规范，以 OpenCode 为主要运行环境；**本仓库不自动配置角色、权限、消息通知或生产操作**。

- [完整协作规范](.agent/collaboration.md)：唯一的角色、触发条件与授权规则来源。
- [统一消息协议](.agent/exchange/README.md)：独立会话信箱与子代理返回的消息语义。
- [沙盒验证](sandbox/README.md)：可复用协议检查、虚构用例与项目接入冒烟说明。

版本通过 Git 提交和标签追溯；工作树只保留现行规范，不按版本复制多份文件。

## 角色与工作流

Lead 是用户的日常入口；Coder、Validator、Reviewer 是任务限定的子代理。Advisor 独立处理重大技术取舍；Auditor 在阶段或系统性问题触发时，独立审阅并直接提供原始报告。六个角色不代表六个常驻窗口或六种必须使用的模型。

普通任务由 Lead 定义范围、调度实现、组织检查并交付；只有命中规范中的条件才增加变更级 Reviewer、系统级 Auditor 或 Advisor 裁决。技术建议、独立验收、用户风险接受与执行授权不能互相替代。完整权限与流程以协作规范为准，此处不重复维护。

## 接入项目

1. 先核对目标项目现行的 `AGENTS.md`、权限与 Git 工作流。按需合并本仓库的 `.agent/`、入口说明及 `.gitignore` 规则；**不要覆盖目标项目已有文件或状态**。
2. 在目标项目的运行时配置角色、工具权限、共同工作目录和共享信箱路径。角色提示词在 `.agent/prompts/`，但复制提示词本身不授予工具权限。
3. 当前独立会话可由用户手动提醒读取信箱；消息写入不等于已送达，`received` 也不代表完成。自动通知属于独立的运行时接入工作。
4. 用 `sandbox/` 的无生产副作用用例先检查协议，再在目标项目的隔离范围内做一次针对真实角色和工具权限的最小冒烟。Kit 内检查通过不能替代目标项目的验收。

需要保存的决策与证据应脱敏归档；`.agent/exchange/tasks/` 是运行消息目录，应按目标项目的 Git 策略排除。

## 本地沙盒检查

需要 Python 3.10+；以下命令只针对仓库内的虚构样例和一次性测试副本：

```bash
python3 -B sandbox/verify_messages.py sandbox/fixtures/messages
python3 -B -m unittest discover -s sandbox/tests -v
```

检查器只判定已实现的结构规则，**不证明**消息作者身份、事实正确性、自动送达或工具权限已生效。消费项目的权限负例必须由相应角色实际调用工具，并保留工具返回；详情见[沙盒说明](sandbox/README.md)。

## 目录

```text
AGENTS.md                    项目入口示例
.agent/
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
```

## 状态与许可

本套件尚未证明对所有项目有效；需用真实任务观察有效发现、误报、返工、用户介入次数和总耗时。文档规则与已配置、已实测的运行时限制应分别标注。

许可：[MIT](LICENSE)。
