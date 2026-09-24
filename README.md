# doc-format-check

检查中文 Markdown 排版，修复机械项，保留语义疑点，并保存前后对比。2.0 默认参考 UTR #59 r1 的字符分类处理混排间距，覆盖汉字扩展区、非 ASCII 字母及完整字素簇。

## 快速使用

Python 3.10+。安装包自带固定的纯 Python 依赖和 Unicode 数据，无需 pip 安装，运行时不联网。Windows 使用 `py -3`，其他平台使用 `python3`。

```powershell
git clone https://github.com/naisi-alibaba/doc-format-check.git
py -3 doc-format-check/scripts/check_format.py document.md
py -3 doc-format-check/scripts/check_format.py document.md --fix --report reports/changes.md
```

报告父目录须预先存在，并位于扫描范围外。只扫不改正文；修复逐文件原子写入，批量不是事务，原文件先由版本控制或范围外备份保存。

```text
中文AI工具        → 中文 AI 工具
𠀀é               → 𠀀 é
收益20%增长        → 收益 20% 增长
C#开发            → C# 开发（中文语境）
决定单独处理      → 保持原文
```

代码、链接、URL、邮箱、HTML标记、实体、转义和配置保护的专名不参与修复。复杂 Markdown 扩展采用保守保护，不宣称完整语法解析。`登陆`、`帐号`等有语境的词默认仅提示。

## 间距配置

```json
{
  "spacing_engine": "utr59",
  "spacing_language": "zh",
  "num_space": "always"
}
```

配置放在文档项目的 `.docformat.json`，逐文件向上发现；`--profile generic` 或显式配置文件不叠加自动发现配置。CLI 的 `--spacing-engine`、`--spacing-language`、`--num-space` 覆盖相应配置。

- `utr59` 是2.0默认，`legacy`仅选择旧中英文/数字间距策略；其他保护、错词及安装修复仍保留。
- 语言为 `zh`、`non-zh` 或 `und`。中文语境的条件符号按N处理；非中文或未知按O处理，不自动猜测。
- `num_space: never`只禁用直接数字边界新增空格；例如 `收益20%增长`变为`收益20% 增长`，百分号策略独立。
- 新间距引擎只补U+0020，不替换已有Unicode空白、不做Unicode正规化。详细边界见 [间距策略](references/spacing.md)。

## 安装技能

```powershell
py -3 scripts/install.py --dest <技能根目录>
```

安装为 `<技能根目录>/doc-format-check/`。同名目标已存在时拒绝覆盖；先保留旧副本或选择新目录。安装器预检必需文件及数据摘要，禁止源码与目标互相包含；`--list`只查看目标。`--dest`只影响指定位置，`--project`不受全局环境变量改写。

## 退出码与2.0迁移

- 检查器0：没有剩余发现；1：仍有格式或待判断项；2：输入、配置或执行失败。
- 安装器0：成功或明确跳过自身目录；2：冲突或预检/复制错误。
- `--fix`现在必须提供范围外的`--report`，旧调用需调整。
- 两个CLI的stdout/stderr始终UTF-8，包括错误信息；程序化调用方按UTF-8解码。
- 缺少包内数据/依赖时明确失败，不下载或静默切换引擎。

## 验证与维护

```powershell
py -3 tools/generate_spacing_data.py --check
py -3 -m unittest discover -s tests -v
```

测试包含原有文件保护与安装测试、UTR59项目策略、Unicode16.0官方字素边界用例、控制台编码、安装后运行、缺资源与幂等。Windows/Linux × Python3.10/3.13的CI以实际运行结果为准。数据升级必须更新固定快照、manifest、生成表、许可与回归结果。

## 来源与许可

项目MIT。[第三方许可与数据来源](licenses/README.md)。UTR #59 r1为2024-12-16草案：本工具参考其分类，按项目风格插入文本空格，不宣称完全实现渲染器字距规范。uniseg0.10.0固定使用Unicode16.0字素数据；类别单独由固定DerivedGeneralCategory表提供，UTR59表单独记录快照版本。

排版参考 [中文文案排版指北](https://github.com/sparanoid/chinese-copywriting-guidelines)。本工具不生成需求、不核实事实，也不保证查出词典以外的所有错误。
