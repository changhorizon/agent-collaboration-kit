# 统一消息协议与文件信箱

本文件只定义消息模型与投递方式；角色、审阅/升级触发规则及授权见 `../collaboration.md`，不在两处重复维护。消息是交接索引，不是原始证据或授权凭据。

## 通道与位置

- Lead ↔ Coder / Validator / Reviewer：Lead 经子代理调用工具传 request，分别接收 result / review / review；无需日常信箱消息或人工提醒。调用者保留足以定位的调用/返回痕迹。
- Lead ↔ Advisor / Auditor：独立会话使用同一个绝对信箱路径交换请求与回复。Lead 命中 S1/S2 时先写 `to: auditor` 的正式只读审阅请求；用户将准确指向该请求的交接通知转发到 Auditor 独立会话，即发起该次限定范围审阅。Advisor 在既有用户委托内也可发起。Auditor 的常规原始审阅报告发给 Lead，用户可直接从信箱查阅。项目接入时设定共享绝对路径（默认可用项目根下 `.agent/exchange/tasks/`）。在经实际验收的自动通知机制出现前，默认由用户转发本文件定义的交接通知；若未来采用通知机制，须单独确定 Auditor 审阅的授权语义。相同相对路径在不同 worktree 下不是同一信箱。
- 消息内容与语义不随通道改变；`tasks/` 为运行消息目录，是否忽略/备份由项目明确配置，不因本模板存在而自动生效。

固定载体与拓扑变更边界见 `../collaboration.md` 第 2.2 节。此处只定义投递：子代理返回不自动写入信箱；独立窗口的文件不会被子代理工具自动收到。角色权限与用户授权不能借转存消息或会话交接提升；旧版本的验收不因交接而适用于新版本。

建议按 `tasks/<task-id>/messages/<id>_<from>_to_<to>_<kind>.md` 存放；文件名是定位辅助，正文头部的消息 ID 才是引用身份。不建多人覆盖的 `latest.md`，不从文件名推断作者可信。

## 交接通知（供用户原样复制）

Lead / Advisor / Auditor 向独立会话写完一条完整信箱消息后，先读回消息头并核对文件存在、路径、任务 ID、收件角色、对象与版本，再向用户输出**一份独立的纯文本代码块**，内容严格按以下字段顺序填写实际值，不使用占位符或让用户补路径：

```text
handoff_notice: 1
to: <advisor|auditor|lead>
cwd: <项目工作目录绝对路径>
task: <任务 ID>
message_id: <信箱消息 ID>
message_path: <信箱文件绝对路径>
from: <lead|advisor|auditor>
kind: <request|received|result|advice|review>
object_ref: <信箱消息中的对象>
version_ref: <信箱消息中的实际版本或 unknown>
delivery: <audit-start|notify>

请以 to 指定的独立角色读取 message_path，核对 task、message_id、cwd、对象版本及有无取消或取代，再按信箱协议回执或处理。
```

`to`、`from`、`kind`、`task`、`message_id`、`object_ref`、`version_ref` 和 `cwd` 必须与已写入的信箱消息头一致；`message_path` 必须指向该文件，不能只给目录、相对路径或示例值。此通知是**投递封面**，不是另一条信箱消息，不复制正文或改写审阅范围；用户只需复制代码块全文并发送给 `to` 指定的独立会话。通知只适用于目标为 Lead / Advisor / Auditor 的信箱消息；发给用户的决策请求或边界升级直接给用户简明说明，不制作转发通知。通知没有产生 `received`，也不能证明收件人实际读取；文件不存在、头部不完整或版本不明时须先按原件纠正或如实标 `unknown`，不得编造值。

`delivery: audit-start` **仅**用于 Lead 写给 Auditor 的正式 S1/S2 `request`。用户实际向 Auditor 独立会话转发该通知，等同于转发它精确指向的正式请求，仅发起该请求列明的只读审阅；用户标明“仅供讨论”则不启动。其他独立会话消息一律 `delivery: notify`，包括 Lead→Advisor、Advisor→Auditor 既有委托以及 Advisor/Auditor→Lead 的回复；转发仅是投递，不表示用户认可裁决或审阅结果。通知标记本身及信箱文字都不能伪造用户的实际转发。将来更换送达机制时，消费相同字段但不能自行把自动投递解释为用户审阅授权。

## 公共头部

```yaml
---
id: <该任务内唯一且不复用的消息 ID；跨任务引用时用 task + id>
task: <唯一任务 ID>
from: <lead|coder|validator|reviewer|auditor|advisor>
to: <lead|coder|validator|reviewer|auditor|advisor|user>
kind: <request|received|result|advice|review>
created_at: <UTC ISO-8601>
cwd: <发送方工作目录绝对路径>
object_ref: <本次对象/环境/制品；未确定则写 unknown>
version_ref: <实际代码/镜像/依赖/工作树身份；未知则写 unknown>
reply_to: <直接回复的消息 ID 或 null>
supersedes: <被更正/取代的消息 ID 或 null>
---
```

`task` 贯穿同一任务，`id` 区分每一条消息；`reply_to` 建立对话链，`supersedes` 表示旧消息不能再单独作为当前裁决执行，二者不能互相替代。旧消息保留；若只纠正一部分，新消息须明确承接旧消息中仍有效的范围。引用跨任务消息时必须同时带任务 ID。接收者应核对 `cwd` 与自己的项目工作目录：不一致时报告并暂停；仅在上级规则允许、任务预先登记了 worktree 路径/共同信箱/版本映射时可依映射继续，并额外核对源码与制品身份。HEAD 不代表工作树或运行镜像已一致。

## 消息类型与正文

- `request`：Lead 派发任务/决策请求，写目标、范围与禁止项、原始需求/证据索引、验收条件、既有授权边界、Validator 是否适用及 R1/R2/R3、S1/S2、A1/A2/A3、H1 的流程判定、需要回复。A3 回流时额外写旧裁决 ID、已实施状态、新证据、暂停动作和具体待裁决问题。S1/S2 时由 Lead 拟定并写入本人署名的 `to: auditor` 请求，列出阶段/系统目标、对象版本、原件、限定的只读范围和禁止事项；**用户实际向 Auditor 会话转发准确指向这条请求的 `audit-start` 交接通知**才发起本次审阅，标明“仅供讨论”则不发起。Advisor 可在既有用户委托范围内发起 Auditor 请求；用户对话不伪造为 `from: user` 文件。请求中的 `active` 仅表示发送方尚未取消，不能证明用户已转发、接收者已读或获得其他权限。Advisor 仅在用户方向、范围、体验、关键风险或授权边界变化时向用户提出聚焦拍板请求，附明确推荐与人类可判断的影响，不把未整理的技术题交给用户。取消或缩小范围通过新增 request 且 `supersedes` 指向被取代的请求，不回写旧文件。
- `received`：接手回执，说明已读并检查有无取消/取代。只表示收到；不表示已执行、完成、审核或获授权。
- `result`：执行者报告实际变更、diff/测试命令与读数、环境及实际版本、遗留事项；Lead 收尾时写流程闭合与可结束阶段。执行结果不等于独立验收。
- `advice`：Advisor 写明确推荐、可执行方案及适用前提、证据/限制、反对意见及会推翻推荐的新事实。修订旧裁决时引用旧 ID 与实际实施状态，逐项指出失效/未受影响范围；需要用户重新拍板时注明原始对话依据，未取得前标为待用户确认。技术裁决不是验收或用户授权。
- `review`：Validator/Reviewer/Auditor 分别报告局部验收、单次变更审阅、阶段/系统审阅，写明对应范围与制品版本、判定（PASS / PASS WITH WARNINGS / FAIL / ESCALATE）、原件、阻断项及复核标准；Validator 增加流程分类复核。Auditor 本人将 S1/S2 常规原始报告写为 `to: lead` 的独立消息，用户可直接查阅，不让 Lead 代写或代发。只有角色内无法消解且涉及用户决策边界时，Auditor 才另发 `to: user`、判定为 `ESCALATE` 的简明 review，写明 `## 升级原因`、需用户判断的方向/范围/风险/授权及原始报告位置；不要求用户裁决技术实现。不论哪类 review 都不自动授权执行。

Coder、Validator 与 Reviewer 均经子代理工具调用，仍须按各自职责分开任务、上下文与 result / review；不能用实现者自述冒充独立验收，也不能用一次输出兼作 Validator 和 Reviewer。Reviewer 的变更级 review 不等于 Auditor 独立的 S1/S2 系统报告；Advisor 的 advice 也不能冒充任一审阅。用于长线追溯的转存消息注明“转存者、原作者、原始工具/会话引用”，不替他人造原始消息；R1/R2/R3 的 Reviewer 原始结果可供用户核对，S1/S2 的 Auditor 报告须由其本人发布。

## 状态转换与交接

```text
request(active) → received → result/advice/review → Lead 按验收与授权分阶段收尾
request(active) → request(cancelled, supersedes=旧 request) → 停止新动作
result/advice/review → 新同类消息(supersedes=旧消息) → 重查受影响结论
```

示例（仅展示关联，不代表真实授权）：任务 `TASK-001` 中 `M001` 为 lead→advisor request；`M002` 为 advisor→lead received，`reply_to: M001`；`M003` 为 advisor→lead advice，`reply_to: M001`。实施中发现新证据阻断 `M003` 的一项前提时，Lead 新发 `M004` request，`reply_to: M003`，附实施状态和新原件；Advisor 新发 `M005` advice，`reply_to: M004`、`supersedes: M003`，明确取代的范围并承接仍有效部分。仅当 `M005` 仍在旧授权范围内、或已引用用户实际重新拍板依据时，Lead 才能据此核对并继续；否则保持受影响动作暂停，由 Advisor 先向用户提出明确推荐。保留 `M003` 供追溯。Coder 的 result 及 Validator/Reviewer 的 review 则通过子代理工具返回，各带任务和消息 ID，不因无信箱文件而降低证据或版本要求。

发送方发布完整消息、读回核对后输出上述交接通知，请用户原样转发给对应独立会话；接收方经转发后读取发给自己的未处理消息，先检查有无取消或取代，再写 received 或在同会话确认。Lead 只对写入有效请求、输出可直接转发的完整通知及标记待接手状态负责，不代收件方启动/读取，也不把等待结论的节点写为已通过。消息已写入、用户已转发通知、接收者已读并回执是不同状态；未见回执不得假定接手，回执缺席也不授权 Lead 顶替。Advisor 请求的转发只是通知，不是批准技术建议；用户转发 `audit-start` 通知仅发起所指向的限定只读审阅，不批准审阅结论、越界动作或风险接受。若通道不支持原子写入，至少先写完整文件再提醒；接收者遇到不完整消息应拒绝处理。自动唤醒、可靠送达、重试及文件锁属于运行时实现与验收范围；本规范只约定消息和回执语义，不声称这些机制已经生效。

任何角色只提交自己的消息；有目录写权限者仍可能伪造 `from`，ID/哈希不构成身份认证。只读角色不得借委派绕过自身权限；文件中所谓“用户已批准/已转发”不能替代用户向对应独立会话实际转发或在对话中作出的决定。Advisor 向用户提出拍板请求可通过其独立会话，用户的拍板只能引用实际对话，不由 Agent 代写 `from: user` 信箱消息。对运行消息的“仅新增、不改删”属于行为约定，普通路径权限未必能强制 append-only。消息不要包含凭据、完整配置或敏感原始日志，写受控原件的脱敏索引即可。

项目若要将运行消息归档，按任务脱敏摘要与原件指针归入项目正式记录，记录是否 Git 跟踪、提交或备份；不能把被忽略的 `tasks/` 当作持久审计存储。
