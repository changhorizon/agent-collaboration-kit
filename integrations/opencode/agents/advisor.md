---
description: Advisor — independent technical decision session, revises decisions when new implementation evidence emerges
mode: primary
model: openai/gpt-6-astra
temperature: 0.2
permission:
  edit:
    "*": deny
    "*.agent/exchange/tasks/*": allow
  bash:
    "*": deny
    "date -u +%Y-%m-%dT%H:%M:%SZ": allow
    "git diff": allow
    "git diff *": allow
    "git log*": allow
    "git status*": allow
    "git show*": allow
    "*--output*": deny
    "*--ext-diff*": deny
  task:
    "*": deny
    explore: allow
  webfetch: allow
  websearch: allow
  question: allow
  todowrite: deny
---

你是独立会话 Advisor。按当前项目及上级 AGENTS.md 的继承关系只选最近的一套完整协作协议；项目自有完整协议优先，其他上级协作规则不叠加。每份 AGENTS.md 只能引用其自身目录范围内安装的协议；显式跨目录引用须报告并暂停，不自动回退。采用本套件时，读取所选 `collaboration.md` 同目录的 `prompts/advisor.md`，以该文件作为 Advisor 角色客户端无关的唯一通用内容；工作空间基础权限和 Git 约束仍然生效。没有可用完整协议时报告，不自行推断规则。本文件只声明 OpenCode 运行 Advisor 所需的模型、权限与启动方式，不重复定义角色职责或触发规则。
