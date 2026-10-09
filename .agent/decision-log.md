# Decision Log

重大技术选择与用户授权分开记载。只追加更正条目，不回写旧结论使其像从未发生；引用原始证据和消息 ID。

## 2026-10-09 D-001 — 客户端无关角色权威的位置与形式

- 关联 task / request / advice / review：Kit 角色定义通用化阶段（Lead 直接实现 + Validator 独立验收）；未命中 A1/A2/A3，未发 Advisor/Auditor 请求。
- 待决问题与选项：客户端无关的角色定义权威放在哪里、以何形式；选项 A=沿用 `.agent/collaboration.md`（语义权威）+ `.agent/prompts/*.md`（通用操作内容），把 `integrations/opencode/agents/*.md` 去重为薄加载器；选项 B=新增单一通用角色文件并让各层指向它；选项 C=引入机器可读 schema（JSON/YAML）。
- 技术推荐及给出者：Lead 推荐选项 A；理由见下。
- 最终选择、选择者与理由：选择 A。`collaboration.md` 已是职责/权限/拓扑/触发/授权唯一规范；`prompts/*.md` 已是与客户端无关的逐角色操作内容，且各客户端按“一次加载一个角色”引用，逐角色文件比单一大文件更贴合加载模型。去重 OpenCode 正文既消除“每客户端重复维护冲突角色规则”的漂移风险，又不新增文件、不改 install.py/检查器、保持可核对。格式沿用 Markdown（选项 C 无现实诉求，若将来需要机器可读 schema 属 A1，应另行交 Advisor）。
- [E] 原始证据、对象与版本：`main@66af5f4` 的 `.agent/collaboration.md`（§2 角色表、§2.1 权限矩阵、§2.2 拓扑）、`.agent/prompts/*.md`（六份“角色差异提示词”）、`integrations/opencode/agents/*.md`（六份含 model/permission frontmatter + 重复角色职责的正文）、`scripts/check_opencode_agents.py`（写死六角色逐字节比较）、`scripts/install.py`（FILES 列表复制 prompts/*.md，不复制 integrations/）；本机 `opencode 1.18.35`、`codex-cli 0.156.1`。隔离加载探针：对 `integrations/opencode/agents/` 六份新定义的临时副本运行 `opencode debug agent <role>`（XDG 目录指向临时目录），6/6 解析为合法定义，name/mode/model/description 正确，prompt 正文均含 `prompts/<role>.md` 指针。
- [A] 未核实前提、未知与影响：模型运行时是否**实际读回** `prompts/<role>.md` 未验证——本轮只证明定义可加载且指针存在于解析后的 prompt，未做真实模型运行冒烟（安全运行需修改全局运行配置或隔离认证，超出本阶段授权），故“运行时读回正确角色内容”仍为未验证项。Codex 子代理委派与独立会话隔离未核实（见 `integrations/codex/README.md`）。
- 可逆性 / 残余风险：全部为 Git 可回溯的 Markdown 改动，可逆；残余风险=本机 `~/.config/opencode/agents/` 在本次基线变更后会出现预期 DRIFT，需用户手动重新同步（本阶段不自动覆盖）。
- 是否需用户授权：否（客户端无关权威位置/格式为可逆的 Lead 结构决策，不触及权限边界或生产执行；用户已明确“不让我选择具体目录或文件格式”）。未就具体目录/格式向用户提问。
- 阶段状态：已执行（Validator 独立验收 = PASS WITH WARNINGS，无阻断；W-1..W-5 为需收口的警告项）。
- 流程判定（R/S/A/H）：R1/R2/R3 未命中（无代码行为变化、职责与权限矩阵未变、可逆文档结构调整）；S1 未命中——本轮为可逆 Markdown 结构重构，六角色职责/权限/触发/拓扑不变，非“重大架构变化”或“重要里程碑”；但前轮 S1（M005）曾覆盖 `integrations/opencode/agents/*.md` 正文，本轮该六份正文被改写，故 M005 结论不套用到新正文，改由本轮 Validator 独立验收覆盖，漂移检查机制本身未变仍可核对；H1 未命中（不涉生产/凭据/资金/不可逆动作）。
- 实施中出现新证据时：无。
- 是否超出用户旧拍板范围：否。
- 哪些新证据会重开决策：若出现需要机器可读角色 schema、或 Codex/其他客户端证明逐角色文件不可加载、或去重后运行时报“读不到 prompts/”的实测证据，则重开。
- 取代旧结论时：无（首次决策）。
