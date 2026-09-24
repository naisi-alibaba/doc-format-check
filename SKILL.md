---
name: doc-format-check
description: 检查中文 Markdown 排版、按项目配置统一写法并修正常见错字。适用于格式检查、批量排版与改动对比；机械项可修复，事实、措辞和语义疑点仅报告。支持独立 CLI 和 PRD 交付后的格式检查，不做内容生成或事实核验。
---

# 中文 Markdown 格式检查

使用确定性脚本处理排版，保留语义疑点和前后对比。目标必须是 Markdown；先读目标及用户指定范围，纯文本即使扩展名为 `.md` 也不要套用 Markdown 规则。

## 最短流程

Python 3.10+，包内带固定纯Python依赖与Unicode数据，运行无需pip或联网。Windows 用 `py -3` 替代下文 `python3`。`<skill-dir>` 为当前技能目录，不写死安装路径。

1. 只扫不写：

   ```bash
   python3 <skill-dir>/scripts/check_format.py <目标.md或目录>
   ```

2. 在用户要求修复、已有版本控制或范围外备份时，应用机械项并保留报告：

   ```bash
   python3 <skill-dir>/scripts/check_format.py <目标> --fix --report <范围外>/format-record.md
   ```

   报告父目录须存在，不能覆盖输入或位于扫描目录内。脚本保留 UTF-8 BOM、CRLF 与硬换行，逐文件原子替换；批量操作不是事务，备份仍有价值。

3. 复查剩余项：退出码 `0` 表示没有剩余发现；`1` 表示仍有格式或待判断项；`2` 表示调用/输入错误。修复后的 `1` 可能只有 B 档，不等于修复未执行。

4. 在对话中列出重要改动和 B 档原句。未确认的事实、优先级、范围和语义不自动修改。用户已有授权不重复询问。

## 混排间距

默认`spacing_engine: utr59`，`spacing_language: zh`；支持`legacy`间距兼容模式和`non-zh/und`语言语境。按完整字素簇插普通空格，保护Markdown、emoji和组合字符，不做Unicode正规化。原始UTR59-r1为草案，句读标点经项目风格过滤；不是中文分词。详见[间距策略](references/spacing.md)。

## 项目配置

显式 `--profile <JSON路径或generic>` 优先，否则按每个目标文件目录向上查找 `.docformat.json`。配置和私有词表留在使用项目，不进入公共技能包。

“帐号”等字形偏好默认只提示。项目确需统一时使用 `typo_fix` 或 `project_names`；可能改变事实的命名继续留给人判断。配置例子见 `profiles/example.json`，规则和保护区详见 [references/rules.md](references/rules.md)。

## 与 PRD 协作

接受已起草的 Markdown，输出机械修正记录与待确认原句。PRD 中的未知指标、未定优先级和开放问题不是应删除的排版错误；保留它们。不要在该步骤修改需求方案或宣称文档已通过业务评审。

## 失败处理

- CLI始终输出UTF-8；程序化调用方按UTF-8解码。缺包内资源时重新取得完整安装包，不静默改用旧引擎。
- 目录扫描跳过符号链接、junction 子目录、版本库和依赖目录；显式目标必须存在且是 Markdown 或目录。
- 编码/配置错误、混合换行与只读报告会在正文修改前报告；修复前检查报告目录可写。
- 若修复改变了内容含义，保留原件，定位对应规则与最小例子，再修改规则或项目配置。

安装说明面向使用者，见仓库 README。无需为了执行本技能加载安装器或设计文档。
