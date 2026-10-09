# 消息填写模板

按 kind 保留相应的正文板块。字段语义、取消与更正规则以 `README.md` 为准；流程触发条件只见 `../collaboration.md` 第 4 节。

```yaml
---
id: <唯一消息 ID>
task: <任务 ID>
from: <角色>
to: <角色或 user>
kind: <request|received|result|advice|review>
created_at: <发布时实际读取的 UTC ISO-8601；无可靠时钟不填猜测值>
cwd: <绝对工作目录>
object_ref: <实际对象或 unknown>
version_ref: <实际版本/工作树身份或 unknown>
reply_to: <直接上游消息 ID 或 null>
supersedes: <被更正消息 ID 或 null>
---
```

## 发信后的用户转发通知（独立会话）

先写信箱消息，再从已落盘的头部填入以下各项实际值；**向用户输出完整代码块，不输出未替换的占位符**。字段规则和 `audit-start` 的生效边界见 `README.md`；这段通知不是信箱消息，也不替代原始请求。

```text
handoff_notice: 1
to: <advisor|auditor|lead>
cwd: <与信箱头一致的绝对项目工作目录>
task: <与信箱头一致的任务 ID>
message_id: <信箱头 id>
message_path: <已写入的信箱文件绝对路径>
from: <lead|advisor|auditor>
kind: <与信箱头一致的消息种类>
object_ref: <与信箱头一致的对象>
version_ref: <与信箱头一致的版本或 unknown>
delivery: <audit-start|notify>

请以 to 指定的独立角色读取 message_path，核对 task、message_id、cwd、对象版本及有无取消或取代，再按信箱协议回执或处理。
```

## request

```text
## 指令状态
active / cancelled
## 目标与原始需求
## 范围、禁止事项与已有改动
## 验收条件与检查计划
## 依据（证据原件 / 假设 / 未知）
## 既有授权边界（注明实际来源）
## 流程判定（是否需独立 Validator 及理由；R1/R2/R3、S1/S2、A1/A2/A3、H1 是否触发、理由；可复用结论 ID 或无）
## S1/S2 独立审阅请求（适用时：Lead 拟定待用户转发或 Advisor 既有委托依据 / 阶段或系统目标 / 审阅对象与版本 / 只读范围与禁止事项 / 原件位置；Lead 不代写用户转发依据）
## A3 裁决回流（适用时：旧裁决与用户原拍板 ID / 已实施状态 / 新原件 / 暂停范围 / 待裁决问题）
## 需要用户重新拍板（仅 Advisor→user 且越出旧边界时：事实风险 / 明确推荐 / 请求确认的范围）
## 需要回复
```

## received

```text
## 接手
已读取哪条 request；是否存在取消或取代；将处理什么。仅表示接手。
```

## result

```text
## 实际结果与差异
## 测试（命令、读数、未运行项）
## 实际运行对象、版本与工作树
## 遗留问题与未验证事项
## 流程闭合（Lead 收尾时填写）
- 触发规则与复用依据：
- Validator 结果（消息 ID / 原件，或不适用及无行为变化依据）：
- Reviewer 结果（消息 ID / 原件）：
- Auditor 独立报告（消息 ID / 原件 / 不适用及依据）：
- Advisor 当前有效裁决（消息 ID、旧裁决的更正链 / 原件）：
- 用户执行授权（对话依据 / 未取得 / 不适用）：
- 实现 / 验证 / 授权 / 部署 / 观察各阶段：
- 本次可结束到哪一步：
```

## advice

```text
## 推荐
## 事实依据、假设与未知
## 选项权衡及风险
## 实施步骤、适用前提、停止条件与重开条件
## A3 修订（适用时：旧裁决 ID / 已实施状态 / 失效前提与下游 / 未受影响部分）
## 用户拍板（不适用 / 待用户确认及需确认范围 / 已获确认的原始对话依据）
```

## review

```text
## 判定（PASS / PASS WITH WARNINGS / FAIL / ESCALATE）
## 审阅角色与范围（Validator：局部验收 / Reviewer：本次变更 / Auditor：S1/S2 阶段或系统目标）
## 验收对象、版本、范围与原件
## 阻断项（每项：违反的条件、原始证据、影响、最小修复、复核标准）
## 流程复核（Validator：分类是否符合实际 diff、漏掉的必经节点及依据）
## 未覆盖与重开条件
## 升级原因（仅 Auditor→user 且判定 ESCALATE：角色内无法消解的用户边界事项 / 原始 to: lead 报告位置 / 人类可判断的影响与推荐）
```
