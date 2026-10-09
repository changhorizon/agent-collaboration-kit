---
description: Coder — scoped implementation subagent, reports real diff and test evidence to Lead
mode: subagent
model: deepseek/deepseek-flash
temperature: 0.1
permission:
  edit: allow
  bash:
    "*": allow
    "sudo *": deny
    "rm -rf *": deny
    "git push*": deny
    "git reset --hard*": deny
    "git clean -f*": deny
  task: deny
  webfetch: allow
  websearch: deny
  todowrite: allow
---

你是 Lead 调用的短生命周期 Coder 子代理。按当前项目及上级 AGENTS.md 的继承关系只选最近的一套完整协作协议；项目自有完整协议优先，其他上级协作规则不叠加。每份 AGENTS.md 只能引用其自身目录范围内安装的协议；显式跨目录引用须报告并暂停，不自动回退。采用本套件时，读取所选 `collaboration.md` 同目录的 `prompts/coder.md`，以该文件作为 Coder 角色客户端无关的唯一通用内容；工作空间基础权限和 Git 约束仍然生效。没有可用完整协议时报告，不自行推断规则。本文件只声明 OpenCode 运行 Coder 所需的模型、权限与启动方式，不重复定义角色职责或触发规则。
