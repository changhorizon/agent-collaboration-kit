# Agent Collaboration Kit

项目无关的候选协作套件。复制本目录到项目根时合并而非覆盖已有 AGENTS.md 和 .gitignore；本模板不自动启用权限、模型或消息投递。`.agent/collaboration.md` 是唯一完整协作规范，消息语法以 `.agent/exchange/README.md` 为准；版本沿 Git 提交和标签追溯，工作树只保留现行内容。

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

本套件采用固定六角色拓扑：Lead、Advisor 是两个主要独立会话；Auditor 在 S1/S2 阶段或系统审阅时低频启动独立会话；Coder、Validator、Reviewer 是 Lead 按需调用的三个新上下文子代理。接入顺序：确认项目现行规则与授权边界 → 设置独立会话的共同绝对工作目录和信箱路径 → 按运行时接线角色/权限/消息通道 → 用无生产副作用的正反例试运行 → 记录哪些机制已实际生效。独立会话的信箱提醒可由人转发；子代理经调用工具返回。两者采用同一消息模型，但不自动互投，也不假定共享工作树意味着隔离工作环境。拓扑变更须由用户明确决定并在项目/阶段边界生效，不随单次任务临时切换。

无生产副作用的沙盒入口见 `sandbox/README.md`。Kit 内协议检查不替代消费项目实际角色权限与工作目录的最小接入冒烟。

不要把忽略运行消息等同于持久备份；需要保存的决定与证据应脱敏归档。成本与质量用真实任务观察（有效发现、误报、返工轮次、用户介入次数、耗时）后再调调用阈值。
