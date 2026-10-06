# 多模型 Agent 协作入口（项目模板）

本文件是复制到项目时的入口示例；先合并项目已有规则，不得直接覆盖。若与项目已有权限、目录或业务不变量冲突，先澄清再接入。

- 协作规范与触发规则：`.agent/collaboration.md`。
- 消息协议、信箱与模板：`.agent/exchange/README.md`、`message-template.md`。
- 项目长期索引：`.agent/project-state.md`、`decision-log.md`、`risk-register.md`、`evidence/`、`milestones/`。
- 角色差异提示词：`.agent/prompts/`；提示词文件不是运行时配置，也不授予工具权限。
- 可复用沙盒用例：`sandbox/README.md`；协议检查通过不等于项目运行权限已验收。

固定协作拓扑：Lead / Advisor 为主要独立会话，Auditor 在 S1/S2 系统审阅时低频使用独立会话，Coder / Validator / Reviewer 仅为 Lead 调用的子代理；消息通道及角色边界见上述唯一规范。单次任务不临时改变角色会话形态。角色缺席或运行权限不满足时报告用户并暂停对应节点；项目/阶段级拓扑变更需用户明确决定与完成交接。

工作前核对当前项目根、实际工作目录、代码与工作树状态；跨会话消息中目录不一致时暂停并报告，不在其他仓库执行交接。默认各窗口使用同一项目目录；仅当上级规则允许且事先登记了各工作树路径与共同信箱绝对路径，才可跨 worktree 工作，并分别核对制品版本。不得默认同名相对路径指向同一文件。
