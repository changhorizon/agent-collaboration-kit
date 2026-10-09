# Ally 角色（可选用户入口）

Ally 是 Agent Collaboration Kit 的可选用户入口角色。它保留六角色的项目内职责与触发规则；启用 Ally 时，用户入口由 Lead 转为 Ally。本文只说明 Ally 的通用设计与已实现/未实现的边界；它不是任何用户授权或原始对话的副本。

## 定位与拓扑

- 未启用 Ally：用户直接使用 Lead，Lead 是项目执行主会话。
- 启用 Ally：用户日常面对 Ally；Lead 仍是项目执行主会话，Advisor / Auditor 仍是独立会话，Coder / Validator / Reviewer 仍由 Lead 经子代理调用。
- Ally 启动 Lead 不构成父子代理关系；Ally 不拥有任何独立角色，也不经调用工具调度 Coder / Validator / Reviewer 子代理。

## 职责边界

- 任务前澄清需求、边界、非目标与限制；工作中在授权范围内只读核对事实与证据、整理交接、把进展反向汇报给用户。
- 不实施业务代码；不替代 Lead 推进项目、Advisor 的重大技术裁决、Validator / Reviewer 的独立核验或 Auditor 的系统审阅。
- 可在已确认任务授权范围内分级代确认常规工具请求；越界、高风险及用户专属决定（业务方向/体验、扩大范围、接受关键风险、生产与凭据/资金）仍交用户本人。
- 不得过滤有证据的阻断项；独立角色的原始结论与不同意见保持可直达、可核对，用户的实际回复才是新的授权来源。

## 交接与消息语义

- 用户 ⇄ Ally 为直接对话；Ally ⇄ Lead / Advisor / Auditor 经共享信箱交接。
- Ally 用 `delegation` 消息交任务，写任务 ID、目标与验收、用户确认的边界与授权范围、原始授权指针、目标项目生效协议、实际 cwd、信箱绝对路径、版本及待核实未知。委托是授权指针，不是授权本身。
- 代传（relay）保留原作者署名与审阅范围，只投递不改写。

## 已实现（静态协议）

- 角色、权限矩阵、会话拓扑：`.agent/collaboration.md`（§2、§2.1、§2.2、§12）。
- 角色内容：`.agent/prompts/ally.md`。
- 消息语义：`.agent/exchange/README.md`（`delegation` kind、`delivered_by`）、`.agent/exchange/message-template.md`。
- 安装与检查：`scripts/install.py`、`scripts/check_opencode_agents.py`、`sandbox/verify_messages.py` 及沙盒测试。

## 未实现 / 未接线（边界）

- 自动会话启动、唤醒或关闭独立角色会话。
- 事件驱动的自动投递与回执。
- Ally 代发起 S1/S2 审阅（`delivered_by: ally` 为未来运行时接线后的保留路径）。
- 分级代确认工具请求的运行时执行。
- 单窗口自动调度。

现阶段 S1/S2 只读审阅仍要求用户本人转发 `audit-start` 交接通知（或 Advisor 在既有用户委托内发起）；Ally 代投与自动投递在接线并实测前不生效、不改变该现行条件，普通 `notify` 的 Ally 自动代投亦未接线。
