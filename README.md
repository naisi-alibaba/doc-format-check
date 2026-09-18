# doc-format-check

中文 Markdown 排版格式检查与错别字修正，按《[中文文案排版指北](https://github.com/sparanoid/chinese-copywriting-guidelines)》实现。以 Agent Skill 形式分发，同一份 bundle 可装进 Claude Code、Codex、DeepSeek Harness、WorkBuddy。

## 核心主张

**格式问题分两档，混在一起做必出事故。**

| | 判据 | 处理 |
| --- | --- | --- |
| **A 档** 机械项 | 改法唯一，不触碰语义 | 自动修（16 条规则） |
| **B 档** 语义项 | 需要事实或人的判断 | 只报不改（13 条规则） |

判档唯一标准：**不看原始材料、不问相关方，能不能确定唯一正确写法。**

这条线是整个工具的骨架。`帐号`→`账号` 可以自动改，因为 `帐号` 在任何语境下都不成词；`登陆`→`登录` 不能，因为「登陆作战」合法。后者只进待确认清单。

## 能做什么

**A 档（自动修）**：中英文加空格、中文与数字加空格、数字与单位加空格、全角标点旁去空格、半角标点转全角、重复标点压缩、全角数字转半角、技术专名大小写（`github`→GitHub）、列表标记补空格、标题与列表前后空行、多余空白清理、错别字修正（中 23 / 英 81 条必错词）。

**B 档（只报）**：有歧义的易混词、第三方名称、绝对化表述、内部标记残留、疑似并列的有序列表、H1 缺失、路径写法不一致、引号风格混用等。

**改前/改后对比记录**：`--report` 产出可逐条复核的 Markdown 记录，错别字单列词级对比。

## 安装

```bash
git clone https://github.com/naisi-alibaba/doc-format-check.git
cd doc-format-check
python3 scripts/install.py --list      # 探测已有的 harness 技能目录
python3 scripts/install.py             # 装进用户级目录
```

> 克隆出来的目录名必须保持 `doc-format-check`。DeepSeek Harness 按目录名注册技能，改名会导致加载失败。

| 环境 | 用户级 | 项目级 | 调用 |
| --- | --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` | 按 description 自动匹配 |
| Codex | `~/.codex/skills/`、`~/.agents/skills/` | `.codex/skills/`、`.agents/skills/` | `/skills` 或 `$` |
| DeepSeek Harness | `~/.dsh/skills/`、`~/.agents/skills/` | `.dsh/skills/`、`.agents/skills/` | `/doc-format-check` |
| WorkBuddy | `WORKBUDDY_SKILLS_DIR` 或 `--dest` | 同左 | 技能选择器 |

安装器会先做契约自检（frontmatter、kebab-case name、目录名一致、无嵌套 SKILL.md），不通过即中止。装完重启 harness。

也可以完全不装，直接当命令行工具用。

## 用法

```bash
# 只扫不改
python3 scripts/check_format.py docs/

# 应用 A 档修复 + 产出对比记录（记录文件要放在扫描范围之外）
python3 scripts/check_format.py docs/ --fix --report /tmp/record.md

# 中文与数字之间不加空格
python3 scripts/check_format.py docs/ --num-space never
```

只用标准库，无第三方依赖。Windows 控制台中文乱码时先设 `PYTHONIOENCODING=utf-8`。

**`--fix` 之前务必有回滚点**：Git 工作区干净，或先备份到扫描范围之外。

## 项目规则用 profile 外挂

专名、菜单路径、第三方名称、业务词表属于项目，不属于工具。写进项目根目录的 `.docformat.json`，脚本会从目标路径逐级向上自动发现：

```jsonc
{
  "heading_level": 3,
  "project_names": [
    { "wrong": ["ACMEOS", "Acme OS"], "correct": "AcmeOS" }
  ],
  "rival_marks": ["CompetitorOS"],
  "typo_fix": [["comaptible", "compatible"]],
  "typo_pairs": [["登陆", "登录"]]
}
```

完整字段见 `profiles/example.json`。`typo_fix` 会被自动修正，`typo_pairs` 只报不改——有歧义的词只能放后者。

## 设计文档

`DESIGN.md` 给出完整的判档决策树、规则顺序依赖图、逐条核查表（每条规则的依据 / 触发条件 / 判档理由 / 可推翻点）、八条不可删的例外，以及五组验证方法。

几条值得先知道的设计取舍：

- **规则顺序即正确性**。所有「加空格」规则必须排在「删全角标点旁空格」之前，否则不幂等。
- **例外比规则值钱**。保护区掩码、品牌白名单、行首 Markdown 语法隔离、分隔线守卫、表格单元格内边距——删任何一条都会改坏文档。
- **争议项不自动改**。指北自己标注为「争议」的条目（链接前后加空格、直角引号方向）只做不一致检测。
- **幂等是硬指标**。`--fix` 后复跑，A 档必须归零。不归零说明规则在互相打架。

## 已知边界

- 词典驱动，**不是全量拼写检查**。词典外的错字、多字漏字、串词一律抓不到。扫完不等于文档没问题。
- 讲格式规则的文档里，反例必须写进反引号，否则会被当成真错误改掉。
- 扩展名是 `.md` 但内容是纯文本稿的文件不适用。

## 相关

- [中文文案排版指北](https://github.com/sparanoid/chinese-copywriting-guidelines)——本工具 A 档空格、标点、全半角规则的规范来源。
- [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills) · [Codex Skills](https://developers.openai.com/codex/skills) · [DeepSeek Harness Skills](https://deepseek-harness.github.io/deepseek-harness/reference/subsystems/skills)——四种 harness 的技能加载约定，本 bundle 按其最严交集构造。

## License

MIT
