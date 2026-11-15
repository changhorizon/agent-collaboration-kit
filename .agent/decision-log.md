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

## 2026-10-09 D-002 — Ally 纳入协议：拓扑/授权变更的触发口径与静态实现

- 关联 task / request / advice / review：Kit Ally 静态协议阶段（Lead 直接实现 + Validator 独立验收）；未发 Advisor/Auditor 请求（判定见“流程判定”）。
- 待决问题与选项：是否把“Ally 委托/代传/代发起审阅/分级代确认”作为 A1 重大长期取舍交 Advisor；选项 A=按 `docs/ally.md` 与 `.agent/collaboration.md` §12 的既定边界直接落静态协议（保守、不扩权）；选项 B=先把委托证据模型交 Advisor 裁决再实现。
- 技术推荐及给出者：Lead 推荐选项 A。
- 最终选择、选择者与理由：选择 A。Ally 的职责、拓扑（可选入口）、权限边界、委托内容与分级代确认边界已在 `docs/ally.md`（通用设计）与用户本次对话确认的目标中列明；本阶段只是把它们转写为协议与消息 schema，属可逆 Markdown/小改 Python，未出现“既定需求无法直接决定”的互斥架构分叉。设计刻意保守：委托是“授权指针而非授权本身”、代发起审阅仅在可追溯委托内、分级代确认严格限于已确认任务范围、“用户本人转发 audit-start”仍为现阶段唯一发起条件（Ally 代投为接线后的保留路径）。
- [E] 原始证据、对象与版本：`docs/ally.md`（公开设计说明，非用户授权原件）与用户本次对话的目标/授权（真实对话，非仓库文件）；`main@a02d965` 的 `.agent/collaboration.md`、`.agent/exchange/README.md`、`sandbox/verify_messages.py`、`scripts/install.py`、`scripts/check_opencode_agents.py`。
- [A] 未核实前提、未知与影响：自动会话启动、自动投递、自动审阅发起、Ally 代确认工具请求的实际运行时行为均未接线/未实测，全部记为未验证；本阶段仅落“协议允许”的静态语义，不宣称已接线。
- 可逆性 / 残余风险：协议与 schema 改动可 Git 回退；残余风险=Ally 尚无可运行的会话载体，启用 Ally 前须先完成运行时接入与权限负例验收。
- 是否需用户授权：本阶段拓扑/授权边界未超出用户在本次对话确认的范围；未就具体 schema/目录询问用户。
- 阶段状态：已实现并本地提交（`e9810eb`）；Validator 独立验收 = PASS WITH WARNINGS（W1..W5 已修正）；Auditor S1 审阅 = PASS WITH WARNINGS——M002 对修正前候选，M004 对旧 `92a89f8`（现重写为 `e9810eb`）的 W-1 传播限定复核，结论「W-1 已收口」；M005→M006 对 `e9810eb`/`3b870e1` 的历史重写限定复核 = PASS WITH WARNINGS，结论「历史重写干净可公开、公开设计依据到位、协议正文与旧候选逐字节一致」。
- 流程判定（R/S/A/H）：A1 未命中——方向与边界用户已确认、语义由 `docs/ally.md` 与 `.agent/collaboration.md` §12 列明、剩余为可逆 schema 选择；R1/R2/R3 未命中（无生产运行/资金/安全权限边界变化，`verify_messages.py`/`check_opencode_agents.py` 的改动仅扩展枚举与结构校验，不改运行时权限）；S1 命中（新增第七角色 + 入口拓扑 + 授权语义属“重大架构变化”），已按 §4 完成限定范围只读审阅链 M001→M002（旧候选）→M003→M004（W-1 收口复核）→M005→M006（历史重写复核）；H1 未命中（不涉生产/凭据/资金/不可逆动作，未触碰全局配置与安装副本）。
- 未决后续事项（均不阻断、不标为已解决）：M004 的 W-5（“代传/notify”与 `delivered_by: ally` 保留值的可读性张力，建议在 §12.3/README 37 补半句明确“接线前所有通知送达仍由用户本人转发”）、W-6（两处未标“现阶段不生效”的措辞，下次顺带补）、W-7（`prompts/auditor.md` 与 OpenCode `auditor.md` 未明说 `delivered_by: ally` 的 audit-start 现阶段不接受，接线时按 §12.4 补 Auditor 核验规程）；M006 的 W-9（D-002 [E] 行的 `main@a02d965` 为基线提交，Ally 变更在 `e9810eb`/`3b870e1`，下次注明）。下次修改协议或接入运行时一并处理。
- 实施中出现新证据时：无。
- 是否超出用户旧拍板范围：否（保守实现，未扩权）。
- 哪些新证据会重开决策：若出现委托证据模型的多方案实质分叉、或用户要求 Ally 可代批准越界/高风险动作、或实现证明“代发起审阅”语义与现行 audit-start 规则冲突，则重开并视情交 Advisor/用户。
- 取代旧结论时：无。

## 2026-10-09 D-004 — D-002 三处澄清（基线 SHA、信箱原件边界、Auditor 请求时态）

- 关联 task / request / advice / review：D-002 的追加澄清，不回写 D-002 旧记录，不改写旧审阅消息。
- 澄清 1（基线 SHA）：D-002 第 28/34 行的 `main@a02d965` 是**基线提交**（客户端无关角色权威阶段）；Ally 变更位于 `e9810eb`（feat：Ally 静态协议）与 `3b870e1`（docs：S1 闭环节点），其后依次为 `69a0cfe`（M006 收口记录）和 `1dd1a69`（本地 plans 目录规则）。读者不应把 `a02d965` 理解为 Ally 最终候选。
- 澄清 2（信箱原件边界）：S1-KIT-ALLY 审阅链 M001–M006 的信箱原件在 `.agent/exchange/tasks/S1-KIT-ALLY/messages/`，被 `.gitignore` 忽略、**未入库**；D-002 中的 M001–M006 消息 ID 仅提供本机本地定位，不构成公开仓库可复取的证据原件。真实授权与原始报告仍回到对应独立会话与本地信箱。
- 澄清 3（Auditor 请求时态）：D-002 第 24 行「未发 Advisor/Auditor 请求」是**实现/初判当时**的状态；随后已按 §4 完成 S1 审阅链 M001→M006（M002/M004/M006 均由 Auditor 本人发布），故该句不适用于最终状态。保留该行历史语义，不作回写。
- 是否需用户授权：否（澄清既有记录，不改协议、不改历史、不扩权）。
- 取代旧结论时：本条目澄清 D-002 的表述口径，不取代其 S1 结论；M004（W-1 收口）、M006（历史重写）各自仍只对应其原审阅对象与限定范围。

## 2026-11-14 D-005 — 有限升级 A1 裁决：当前状态投影与本地工具强制边界

- 关联 task / request / advice：KIT-UPGRADE-NEXTGEN-001 / M001（lead→advisor A1 请求）→ ADVISOR-M002（advisor→lead advice）。用户已转发，本会话已读、核对无取消/取代，采纳为当前技术基线。
- 待决问题与选项：A1-Q1「当前有效状态」落点（A=Lead 维护 / B=工具派生 / C=混合）；A1-Q2「工具强制边界」（哪些 fail-closed、哪些只靠协议+检查器）。
- 技术推荐及给出者：Advisor 裁决 Q1=C（混合，但非“工具算真实状态、Lead 盖章”：工具生成可重建的消息关系/证据投影，Lead 是唯一执行状态维护者，核对适用性/授权/预算/暂停边界，无法推导的标 unknown 且不靠 Lead 确认提高证据等级）；Q2=逐项（消息唯一性=强制唯一发布+拒绝覆盖，不强制全局顺序号、不建抢号服务；预算=派发前核对为规则前置，台账 `--check` 是预检，要宣称防重复消费须同一作用域内原子「核对并预占」，本轮未接真实调用入口故不能称已 fail-closed 阻止派发；候选与证据=身份/保全是采信前置，显式调用的保全工具，非自动捕获）。
- 最终选择、选择者与理由：接受 Advisor 裁决并入唯一计划。理由：与本仓库既有分层（历史关系/投递接手/可执行性）一致，边界清晰不越平台，复用现有 `verify_messages.py` 能力而非重复实现，且明确本轮不接运行时接线/安装迁移。
- 设计输入的修正（Advisor 指出，已采纳）：
  1. 「PASS 需已知版本」已存在于 `verify_messages.py:116-121`，设计稿误列为新增能力，改为「复用」。
  2. 设计稿 §1 称陈旧索引是「S2 客观触发活例」与 M001「不触发 S2」口径冲突。澄清：陈旧 `project-state.md`（HEAD 66af5f4 vs 实际 5ffccce）是**上一阶段遗留**的「状态与实际候选不一致」实例，本任务开始时已修正；本任务自启动以来未客观命中任何 S2 条件（无预算消耗、无同类 FAIL、无作废工作量），故不触发本任务 S2，也不由 Lead 或 Advisor 擅自启动 Auditor。若后续实现中客观命中，按 §4.2 报告并拟审阅请求。
  3. 不采用「实际执行 > 隔离演练 > 夹具 > 摘要」的全局证据等级排序；改为记录「主张—对象/版本—被执行路径—环境—原件—覆盖/未覆盖」，证据只支持其覆盖的主张。
  4. 工具写预占/档案有副作用，设计稿「所有工具无副作用」改为「只读优先，写入仅限获准协作目录、作用域明确、可追溯且不覆盖原件」。
  5. 本轮不扩大到安装迁移实现（`install.py` 升级留后续）。
- [E] 原始证据、对象与版本：`ADVISOR-M002`（advisor→lead advice，cwd 本仓库）；本仓库 `collaboration.md:188-212,214-237,245-251`、`sandbox/verify_messages.py:116-121,130-191,199-205`、`scripts/install.py:49-57,60-91`；Quant 只读来源见 M002「依据」节（不构成本项目授权）。
- [A] 未核实前提、未知与影响：工具的具体原子发布/并发预占机制由 Coder 实现并用并发负例证明，尚未实现；「本地拒绝超额」可验收，但「真实运行时旁路是否可绕过」未验收（未接线）。
- 可逆性 / 残余风险：协议改写为 Git 可回溯 Markdown、工具为纯本地 Python，可逆；残余风险=工具箱能力易被误读为运行时强制（须在工具输出与文档标注「未接运行时」）。
- 是否需用户授权：实现授权已获用户明确确认——用户在本对话对「范围与资源一次性确认」选择“按设计确认并推进（推荐）”，其选项文案明确包含“等 Advisor 裁决后进入协议定向改写 + 工具 + 独立验证”，据此授权协议/模板改写与最小工具实现。M001 的“未授权：实现协议改写”是 M001 时点（在用户后续选择“按设计确认并推进”之前）的状态，之后由上述用户决定更新；二者不并存为冲突。未授权范围仍为：推送/发布、改 Quant、运行时接线、安装迁移、生产操作。
- 阶段状态：裁决已采纳。协议/模板改写由 Lead 直接实现并过 Validator（PASS WITH WARNINGS，六项验收条件全过、无文本阻断）；因实际 diff 命中 R2/R3（跨模块职责边界/契约变化），变更级 Reviewer 待补齐；工具实现与工具验收待后续。
- 流程判定（R/S/A/H）：A1 命中已交 Advisor 并裁决；实现 diff 重判后 **R2/R3 命中**（§4.1 Advisor 边界、§3.1.4 预算硬前置、§7 验收集合构成跨模块职责边界变化，且跨模块行为无法由局部测试证明）→ 待 Reviewer 变更级审阅；S1/S2 不触发（见修正 2）；H1 未命中。
- 实施中出现新证据时：无。
- 哪些新证据会重开决策：出现必须多写者并发修改同一预算、稳定快照/原始返回在现有客户端无法取得、局部投影须理解任意自然语言、或获准原型证明手工步骤成本仍不可接受 → A3 回流；需要自动会话/投递/运行时权限/新存储/扩大目标或接受无法隔离的关键风险 → 用户边界重开。
- 取代旧结论时：无（首次裁决）。

## 2026-11-14 D-006 — 本地协作工具实现与验证收口（scripts/collab.py）

- 关联 task / request / advice / review：KIT-UPGRADE-NEXTGEN-001 的工具实现阶段（Coder 实现 + Validator 验收 + Reviewer 变更级审阅）。
- 待决问题与选项：本地工具以何形态实现（单一 `scripts/collab.py` CLI 少量子命令 vs 多脚本/大一统），及“唯一发布/台账/保全/状态投影”四能力的强制边界。
- 技术推荐及给出者：按 ADVISOR-M002 A1-Q2（逐项强制、显式调用、一次性、只读优先、写入仅限协作目录、不含 watcher/自动投递/自动派发/代授权/改权限）实现；Lead 指定单一 CLI 复用 `sandbox/verify_messages.py` 单一事实源。
- 最终选择、选择者与理由：`scripts/collab.py` 四个子命令（publish/ledger/preserve/state），importlib 复用 verify_messages 的字段/角色/kind/parse/validate。发布前做目录级完整校验；ledger 原子“核对并预占”且输出不宣称运行时门禁；preserve 候选身份含 git 基线、区分原作者/转存者；state 三平面投影、冲突抑制。理由：复用单一事实源、不建服务、守住平台边界。
- 验证结果：Validator 首轮 FAIL（B1 publish 未做目录级完整校验、B3 缺缺失原件负例、W1 基线未绑定、W5 ledger check fail-open）→ Coder 修复 → Validator 复验 PASS WITH WARNINGS（B1/B3/W1/W5 闭合，73 测试通过）；Reviewer R2/R3 增量审阅 = PASS WITH WARNINGS（无阻断，12 条 W 级警告）。
- [E] 原始证据、对象与版本：`scripts/collab.py`（untracked，2116 行）、`sandbox/tests/test_collab_tool.py`（untracked，971 行）；`python3 -B -m unittest discover -s sandbox/tests -v` = 73 tests OK；`sandbox/verify_messages.py sandbox/fixtures/messages` = PASS 9/3。Reviewer/Validator 子代理返回经 task 工具回传（未落盘信箱，属子代理通道）。
- [A] 未核实前提、未知与影响：真实运行时旁路未验收（未接线）；工具未安装到消费项目（install.py 不含，属安装迁移范围外）；fcntl 仅 Unix；多用户共享信箱 0600 权限未验。
- 可逆性 / 残余风险：新增本地脚本，可 Git 回退；残余风险=工具能力易被误读为运行时强制/作者认证/授权记录（工具已自标注不提供）。
- 是否需用户授权：否（在用户“按设计确认并推进”授权内实现 + 独立验证；未提交/推送/安装）。
- 阶段状态：已实现并过 Validator + Reviewer（均 PASS WITH WARNINGS）；收尾后更新 project-state；未提交未推送。
- 流程判定（R/S/A/H）：R2/R3 命中（协议 diff 与工具 diff 均已过 Reviewer 变更级审阅）；A1 已裁决；S1/S2 不触发；H1 未命中。工具实现本身不新增 A1。
- 未决后续事项（均不阻断、不标已解决，待后续处理）：Reviewer W1–W12（优先 W1 publish 跨角色作者声明、W2 ledger 终态 call_ref 复用、W4 publish TOCTOU/同 ID 并发、W5 写入范围未限定、W6 archive 无秘密检测；其余 W3/W7–W12 为文档/权限/退出码/可移植性/低概率可追溯）。安装迁移、Ally 离线回放、运行时接线均为已确认的后续独立阶段。
- 实施中出现新证据时：无。
- 哪些新证据会重开决策：工具需作为防重复消费/唯一发布/作者认证的可依赖入口、或要安装到消费项目、或 verify_messages 语义变化、或真实任务出现同 ID 并发/秘密归档/多用户信箱 → 重开并按对应范围处理。
- 取代旧结论时：无。

## 2026-11-14 D-007 — Ally 离线回放价值初判

- 关联 task / request / advice / review：Ally 离线回放评估（Lead 直接执行，无 A1/无 R/S/H 触发）。
- 待决问题与选项：是否在启用 Ally 前先做离线价值评估；用何方法（Lead 自评 vs 新上下文子代理模拟 Ally）。
- 技术推荐及给出者：Lead 采用新上下文子代理按 Ally 职责模拟，避免 Lead 既有上下文的偏置；对照 Quant 脱敏协作片段的 ground truth 与 4 项失败判据打分。
- 最终选择、选择者与理由：4 个脱敏场景（重复指挥/取代链/分层审阅/方案vs实施批准）各 5 问，新上下文模拟 Ally 回答；结果 4/4 正确、0 命中失败判据。
- [E] 原始证据、对象与版本：`.agent/evidence/ally-offline-replay-2026-11-14.md`；只读来源为 Quant 项目的若干协作消息链（已脱敏，任务编号/路径/业务不写入本仓库）。
- [A] 未核实前提、未知与影响：脱敏片段隐含关键字段，未测噪音/原始消息；未测 `scripts/collab.py state` 辅助效果；未用完整 `prompts/ally.md`；非真实接线会话，不证明运行时/权限隔离/多项目表现。
- 可逆性 / 残余风险：纯评估无代码/协议变更，无回退风险；残余风险=把「离线价值初判」误读为「已证明可启用」。
- 是否需用户授权：否（只读评估，未启用 Ally、未接运行时、未代授权）。
- 阶段状态：评估完成，结论「有潜力，但不足以默认启用」；是否进入有限试用由用户决定。
- 流程判定（R/S/A/H）：不触发（无代码/协议/契约变更，非阶段里程碑，无生产/授权动作）。
- 未决后续事项：Ally 有限试用（需用户明确授权，不增验收层、不默认高风险工具代确认、保留独立直达通道）；失败判据（增加转述/重复审查、误判授权、隐藏异议、代 Lead 重排）已建立为可操作标准。
- 实施中出现新证据时：无。
- 哪些新证据会重开决策：若需启用 Ally 或接线运行时，须另行立项并重判；若回放扩展到噪音/多项目场景，按结果修订初判。
- 取代旧结论时：无。

## 2026-11-15 D-008 — 安装迁移（install.py 版本戳/冲突/恢复）

- 关联 task / request / advice / review：KIT-UPGRADE-NEXTGEN-001 的安装迁移轮次（Coder 实现 + Validator 验收，无 Advisor/Reviewer 触发）。
- 待决问题与选项：install.py 升级以何形态提供版本戳、升级、冲突可见与恢复；是否作为 A1 交 Advisor。
- 技术推荐及给出者：Lead 判定无 A1 级取舍，直接实现（版本戳 `.kit-version.json`、`--upgrade`/`--force`/`--backup-dir`、manifest 分类 add/unchanged/changed/restore/preserve、状态文件 preserve/restore/拒绝非普通、原子 staging + 备份、不碰 `.agent/`）。
- 最终选择、选择者与理由：如上实现。理由：方向由原任务重点 #6 与交接备忘明确（辨认已装/目标版本、覆盖清单、冲突可见、恢复路径、不覆盖运行数据），无互斥分叉。
- 验证结果：Validator 首轮 PASS WITH WARNINGS（W1 状态文件 preserve 语义对 symlink/目录/缺失不成立、W2 upgrade 未校验源、W4 文档未同步）→ Coder 修复 → Validator 复验 PASS WITH WARNINGS（W1/W2/W4 闭合、W3 闭合；残留 R1 非清单文件静默删除、R2 备份失败误报、R3 AGENTS.md 非原子，均低风险非阻断）。
- [E] 原始证据、对象与版本：`scripts/install.py`、`sandbox/tests/test_install.py`、`README.md`（相对 HEAD=1404742 未提交）；`python3 -B -m unittest discover -s sandbox/tests -v` = 93 tests OK；`git diff --check` 干净。
- [A] 未核实前提、未知与影响：未在 Python 3.10 实机跑（本机 3.12.13，仅语法解析通过）；未测 Windows/跨平台、崩溃一致性、并发 upgrade、真实消费项目。
- 可逆性 / 残余风险：Git 可回溯；残余风险=R1（安装目录内非清单文件被静默删除）、R2/R3（备份失败误报、AGENTS.md 非原子），已记 risk-register R-003。
- 是否需用户授权：否（在用户「按顺序推进」授权内实现 + 独立验证；未提交前已由用户确认范围）。
- 阶段状态：已实现并过 Validator（PASS WITH WARNINGS），待提交；未推送、未安装到消费项目。
- 流程判定（R/S/A/H）：R1/R2/R3 不触发（增量 CLI + 版本戳，默认首次安装契约保持，upgrade 显式且状态文件保留、冲突需 --force 且备份，行为集中可局部测试）；A1 不触发；S1/S2 不触发；H1 未命中。
- 未决后续事项（均不阻断、不标已解决）：R1/R2/R3（见 risk-register R-003）；安装迁移后仍缺「版本发布（tag+push）」与「安装到 Quant」两独立阶段（均需用户另行授权）。
- 实施中出现新证据时：无。
- 哪些新证据会重开决策：若要求跨平台/崩溃一致性/并发安全、或 R1/R2/R3 提升为验收要求、或要绑定未提交 diff 内容哈希作候选身份 → 重开。
- 取代旧结论时：无。
