# Project State（长期索引）

本文件指向当前目标与关键原件，不是原始证据。只填项目已核实的内容；未知写 unknown，不把旧会话推断升格为事实。

## 当前目标与工作对象

- 任务 ID / 目标：KIT-UPGRADE-NEXTGEN-001 / 基于 Quant 协作实践升级 agent-collaboration-kit，减少重复指挥、重复审批、人工搬运消息、候选与报告错位、事后补找证据，同时保留用户授权、独立审阅与原件可追溯。
- 范围 / 不做事项：第一阶段有限升级设计（已落盘 `plans/2026-11-14_001_nextgen-collab-upgrade.md`，本地）+ 协议/模板定向改写 + 最小工具集 + 独立验证 / 不重写整套协议、不建 Agent 调度平台、不接自动投递/自动会话/Ally 代发起审阅、不做 Codex 适配、不改 Quant、不自动推送/发布/安装到消费项目。
- 项目根与共享信箱绝对路径：/mnt/stage/workspace/projects/ai/agent-collaboration-kit ／ .agent/exchange/tasks/（本任务 `KIT-UPGRADE-NEXTGEN-001`）。
- 当前候选（代码 commit + 工作树状态 / 制品版本 / 依赖）：HEAD=`5ffccce`（领先 origin/main 8 提交，未推送）。工作树未提交改动：`.agent/collaboration.md`（§3.1.2/§3.1.4/§4.1/§6.1/§7 改写，Lead 直接实现）、`templates/project-state.md`（新增当前有效状态节）、`.agent/prompts/lead.md`（同步）、`scripts/collab.py` + `sandbox/tests/test_collab_tool.py`（本地工具，Coder 实现，已修 B1/B3/W1/W5）；运行状态 `decision-log.md`（D-005）、本索引 `project-state.md`、`risk-register.md`（R-001=Open，上一阶段填充的未提交运行状态，本轮未改动）。设计稿在 Git 忽略的 `plans/`，非候选。上轮 S1-KIT-001 状态已由 decision-log.md D-001/D-002/D-004 收口。
- 目标环境、服务或进程：不适用（规范与工具升级，无运行时目标环境；工具为 Python 3.10+ 仅标准库）。

## 当前有效决定、授权与待投递入口

- 当前有效入口（按“技术问题/请求链 + 收件范围”，每条链一个）：A1-Q1/Q2 已由 ADVISOR-M002 裁决（Q1=混合/三平面，Q2=逐项强制），D-005 采纳，无待用户决定项。
- 已获授权的动作（引用真实用户决定）：用户在本对话对「范围与资源一次性确认」选择“按设计确认并推进（推荐）”，授权“进入协议定向改写 + 工具 + 独立验证”（预算 Coder≤2、Validator≤2、Reviewer≤1、Advisor 仅 M001 往返、Auditor 不触发）。未授权：推送/发布、改 Quant、运行时接线、安装迁移、生产操作。
- 待投递 / 待接手 / 待裁决：无待投递消息；M001→ADVISOR-M002 往返已完成（用户已转发）。
- 状态投影来源：信箱 `KIT-UPGRADE-NEXTGEN-001/`（M001、ADVISOR-M002）；裁决正文以 ADVISOR-M002 为准。

## 预先约定的验收条件与流程判定

- 验收条件 / 对应任务消息：设计稿六节 + ADVISOR-M002 裁决（已收并采纳）+ Validator 验收协议/模板改写（已 PASS WITH WARNINGS）+ Reviewer 变更级审阅（待）+ 工具实现与验收（待）。
- Validator 是否适用及理由；R1/R2/R3（Reviewer）、S1/S2（Auditor）、A1/A2/A3、H1 分类与依据：A1 已命中并已裁决（ADVISOR-M002，采纳）。协议/模板改写按实际 diff 命中 R2（跨模块职责边界变化：§4.1 Advisor 边界、§3.1.4 预算硬前置、§7 验收集合）与 R3（跨模块行为无法由局部测试证明）→ 待 Reviewer 变更级审阅。S1/S2 不触发（本任务无预算超限/同类 FAIL/作废工作量；历史索引陈旧已修正，不构成本任务 S2）；H1 未命中。
- 可复用结论：无（新任务）。

## 分阶段状态（附证据或消息 ID）

- 实现：协议/模板/lead.md 改写已完成（Lead 直接实现）；`scripts/collab.py` 本地工具已实现（Coder，已修 B1/B3/W1/W5）。
- 独立验证：协议/模板改写 = PASS WITH WARNINGS（Validator）；工具首轮 = FAIL（Validator），修复后复验 = PASS WITH WARNINGS（B1/B3/W1/W5 闭合，73 测试通过）。
- 变更级 Reviewer / 阶段或系统级 Auditor：协议/模板 diff 已过 Reviewer（PASS WITH WARNINGS，B1–B4 闭合）；工具 diff 已过 Reviewer R2/R3 增量审阅（PASS WITH WARNINGS，无阻断，W1–W12 残余）。两轮 Reviewer 与 Validator 报告均经 task 工具回传（子代理通道，未落盘信箱）。
- Advisor：M001（lead→advisor A1-Q1/Q2）→ ADVISOR-M002（advisor→lead advice）已回并采纳（见 decision-log.md D-005、设计稿 §8）。
- 执行授权：用户已一次性确认范围与资源（本对话）。
- 部署：不适用。
- 目标环境观察：不适用。
- 当前可收尾到哪一步：本阶段（协议改写 + 最小工具 + 独立验证）已完成并通过 Validator/Reviewer（均 PASS WITH WARNINGS，无阻断），**已提交**（629890c / 3d3e8d5 / c66eb39，未推送，main 领先 origin/main 11 提交）。Ally 离线回放已完成（见 decision-log.md D-007、evidence/ally-offline-replay-2026-11-14.md）。安装迁移、运行时接线、Quant 重新安装为后续独立阶段。

## 关键事实、假设和原件索引

关键事实：主张 / 对象 / 版本 / 采集方式与时间 / 原件位置 / 证明范围 / 未覆盖事项。标记 [E] 证据、[A] 未验证假设、[I] 有前提的推断。

- F-001：[E] 现状核对（HEAD 5ffccce、权威源、适配、安装入口、工具能力）见设计稿 §1。
- F-002：[E] Quant 三类问题证据索引见设计稿 §2（只读来源，未改 Quant）。
- 假设与未验证事项：[A] 工具集（唯一发布/台账预占/候选保全/状态投影）仅设计未实现；具体原子发布与并发预占机制待 Coder 实现 + 并发负例证明；「本地拒绝超额」可验收，真实运行时旁路未接线未验收。
- 被新证据推翻的旧结论 ID / 下游待复核 ID：无。

## 阻断与风险

- 阻断项（对应验收条件、原件、最小修复、复核标准）：无阻断项（协议/模板与工具均过 Validator + Reviewer，PASS WITH WARNINGS）。残余警告见 risk-register.md R-002（工具 W1–W12，非阻断）。
- 风险与已接受风险（不能将 FAIL 改为 PASS）：本索引曾过时（HEAD 落后 8 提交），已修正并保持同步；R-001（跨项目 cwd）仍 Open；R-002（工具残余警告）Open。工具能力易被误读为运行时强制/作者认证/授权记录，须在输出/文档标注“未接运行时”。
- 已实施裁决的新证据阻断（旧裁决 ID / 实施状态 / 暂停范围 / 已发送的 A3 request / Advisor 修订或待回复）：不适用（已采纳 ADVISOR-M002，无新证据推翻）。

## 授权边界与下一动作

- 既有日常开发授权：Lead 维护项目状态索引、记录决策与审阅结论、直接实现协议/模板改写（已在授权内）、只读研究 Quant 来源证据。
- 高风险执行授权：无；未取得（不推送、不发布、不改 Quant、不改消费项目）。
- 动作 / 负责人 / 停止点 / 重开条件：本阶段已提交（未推送）。后续独立阶段（另行立项）：安装迁移（install.py 版本戳/冲突可见）、运行时接线与真实旁路验收、Quant 重新安装、Ally 有限试用（D-007 结论「有潜力但不足默认启用」）。工具 W1–W12 与 R-002 待后续处理。
- 最后核对日期、工作目录及更新者：2026-11-14T12:40Z / /mnt/stage/workspace/projects/ai/agent-collaboration-kit / Lead。
