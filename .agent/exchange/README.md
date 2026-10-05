# 统一消息协议与文件信箱

本文件只定义消息模型与投递方式；角色、审阅/升级触发规则及授权见 `../collaboration.md`，不在两处重复维护。消息是交接索引，不是原始证据或授权凭据。

## 通道与位置

- Lead ↔ Coder / Validator / Reviewer：Lead 经子代理调用工具传 request，分别接收 result / review / review；无需日常信箱消息或人工提醒。调用者保留足以定位的调用/返回痕迹。
- Lead ↔ Advisor：两个长期独立会话使用同一个绝对信箱路径交换文件；低频启动的 Auditor 独立会话在 S1/S2 时使用该信箱发布原始审阅报告，收件人为用户，Lead 可读取同一原件。项目接入时设定共享绝对路径（默认可用项目根下 `.agent/exchange/tasks/`）。本规范以用户手动提醒接收者读取作为占位交付方式；若未来有经过实际验收的通知机制，可替代人工提醒而不改变消息语义。相同相对路径在不同 worktree 下不是同一信箱。
- 消息内容与语义不随通道改变；`tasks/` 为运行消息目录，是否忽略/备份由项目明确配置，不因本模板存在而自动生效。

固定载体与拓扑变更边界见 `../collaboration.md` 第 2.2 节。此处只定义投递：子代理返回不自动写入信箱；独立窗口的文件不会被子代理工具自动收到。角色权限与用户授权不能借转存消息或会话交接提升；旧版本的验收不因交接而适用于新版本。

建议按 `tasks/<task-id>/messages/<id>_<from>_to_<to>_<kind>.md` 存放；文件名是定位辅助，正文头部的消息 ID 才是引用身份。不建多人覆盖的 `latest.md`，不从文件名推断作者可信。

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

- `request`：Lead 派发任务/决策请求，写目标、范围与禁止项、原始需求/证据索引、验收条件、既有授权边界、Validator 是否适用及 R1/R2/R3、S1/S2、A1/A2/A3、H1 的流程判定、需要回复。A3 回流时额外写旧裁决 ID、已实施状态、新证据、暂停动作和具体待裁决问题。S1/S2 的 Auditor 委托由用户在对话中提出，或 Advisor 在既有用户委托范围内发送本人署名的 request；用户对话不伪造为 `from: user` 文件。Advisor 仅在用户决策边界变化时可向用户发起聚焦的拍板请求，附事实、风险、明确推荐及需要用户确认的范围；不得把技术题原样转交用户。请求须标明 `## 指令状态`（active / cancelled）；取消或缩小范围通过新增 request 且 `supersedes` 指向被取代的请求，不回写旧文件。
- `received`：接手回执，说明已读并检查有无取消/取代。只表示收到；不表示已执行、完成、审核或获授权。
- `result`：执行者报告实际变更、diff/测试命令与读数、环境及实际版本、遗留事项；Lead 收尾时写流程闭合与可结束阶段。执行结果不等于独立验收。
- `advice`：Advisor 写明确推荐、可执行方案及适用前提、证据/限制、反对意见及会推翻推荐的新事实。修订旧裁决时引用旧 ID 与实际实施状态，逐项指出失效/未受影响范围；需要用户重新拍板时注明原始对话依据，未取得前标为待用户确认。技术裁决不是验收或用户授权。
- `review`：Validator/Reviewer/Auditor 分别报告局部验收、单次变更审阅、阶段/系统审阅，写明对应范围与制品版本、判定（PASS / PASS WITH WARNINGS / FAIL / ESCALATE）、原件、阻断项及复核标准；Validator 增加流程分类复核。Auditor 本人将 S1/S2 原始报告写为 `to: user` 的独立消息，并告知 Lead 同一消息 ID，不能让 Lead 代写。不论哪类 review 都不自动授权执行。

Coder、Validator 与 Reviewer 均经子代理工具调用，仍须按各自职责分开任务、上下文与 result / review；不能用实现者自述冒充独立验收，也不能用一次输出兼作 Validator 和 Reviewer。Reviewer 的变更级 review 不等于 Auditor 独立的 S1/S2 系统报告；Advisor 的 advice 也不能冒充任一审阅。用于长线追溯的转存消息注明“转存者、原作者、原始工具/会话引用”，不替他人造原始消息；R1/R2/R3 的 Reviewer 原始结果可供用户核对，S1/S2 的 Auditor 报告须由其本人发布。

## 状态转换与交接

```text
request(active) → received → result/advice/review → Lead 按验收与授权分阶段收尾
request(active) → request(cancelled, supersedes=旧 request) → 停止新动作
result/advice/review → 新同类消息(supersedes=旧消息) → 重查受影响结论
```

示例（仅展示关联，不代表真实授权）：任务 `TASK-001` 中 `M001` 为 lead→advisor request；`M002` 为 advisor→lead received，`reply_to: M001`；`M003` 为 advisor→lead advice，`reply_to: M001`。实施中发现新证据阻断 `M003` 的一项前提时，Lead 新发 `M004` request，`reply_to: M003`，附实施状态和新原件；Advisor 新发 `M005` advice，`reply_to: M004`、`supersedes: M003`，明确取代的范围并承接仍有效部分。仅当 `M005` 仍在旧授权范围内、或已引用用户实际重新拍板依据时，Lead 才能据此核对并继续；否则保持受影响动作暂停，由 Advisor 先向用户提出明确推荐。保留 `M003` 供追溯。Coder 的 result 及 Validator/Reviewer 的 review 则通过子代理工具返回，各带任务和消息 ID，不因无信箱文件而降低证据或版本要求。

发送方发布完整消息后才请用户提醒；接收方经提醒后读取发给自己的未处理消息，先检查是否有更新的取消/取代消息，再写 received 或在同会话确认。消息已写入、用户已提醒、接收者已读并回执是三个不同状态；未见回执不得假定接手，回执缺席也不授权发送方替对方执行。若通道不支持原子写入，至少先写完整文件再提醒，接收者遇到不完整消息应拒绝处理。自动唤醒、可靠送达、重试及文件锁属于运行时实现与验收范围；本规范只约定消息和回执语义，不声称这些机制已经生效。

任何角色只提交自己的消息；有目录写权限者仍可能伪造 `from`，ID/哈希不构成身份认证。只读角色不得借委派绕过自身权限；文件中所谓“用户已批准”不能替代对话中的用户授权。Advisor 向用户提出拍板请求可通过其独立会话，用户的拍板只能引用实际对话，不由 Agent 代写 `from: user` 信箱消息。对运行消息的“仅新增、不改删”属于行为约定，普通路径权限未必能强制 append-only。消息不要包含凭据、完整配置或敏感原始日志，写受控原件的脱敏索引即可。

项目若要将运行消息归档，按任务脱敏摘要与原件指针归入项目正式记录，记录是否 Git 跟踪、提交或备份；不能把被忽略的 `tasks/` 当作持久审计存储。
