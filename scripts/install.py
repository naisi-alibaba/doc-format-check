#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doc-format-check · 多环境安装器

把本技能 bundle 装进 Claude Code / Codex / DeepSeek Harness / WorkBuddy。
四者消费的是同一份 SKILL.md 契约，所以装的是同一个目录，不做分叉。

用法：
  python3 install.py --list                      # 只探测，不动文件
  python3 install.py                             # 装进所有探测到的用户级目录
  python3 install.py --targets claude,codex      # 只装指定环境
  python3 install.py --project .                 # 装进项目级目录
  python3 install.py --dest <任意目录>            # 装进自定义目录（WorkBuddy 等）
  python3 install.py --link                      # 用符号链接代替复制（POSIX）
  python3 install.py --uninstall                 # 移除已装副本
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
try:
    from unicode_adapter import validate_resources
except (ImportError, OSError, ValueError) as exc:
    if __name__ == '__main__':
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
        print('Incomplete installer runtime: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
    raise

BUNDLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE_NAME = os.path.basename(BUNDLE_DIR)
# bundle 只包含这些；私有 profile 在项目目录里，不随技能分发
BUNDLE_ITEMS = ['SKILL.md', 'README.md', 'DESIGN.md', 'LICENSE', 'scripts', 'profiles', 'references', 'data', 'licenses', 'VERSION', 'CHANGELOG.md']

USER_HOME = os.path.expanduser('~')

# 各环境的发现路径。agents 是 Codex 与 DSH 都认的中立目录，优先用它可少装一份。
USER_TARGETS = {
    'claude': os.path.join(USER_HOME, '.claude', 'skills'),
    'codex': os.path.join(USER_HOME, '.codex', 'skills'),
    'agents': os.path.join(USER_HOME, '.agents', 'skills'),
    'dsh': os.path.join(USER_HOME, '.dsh', 'skills'),
}
PROJECT_TARGETS = {
    'claude': os.path.join('.claude', 'skills'),
    'codex': os.path.join('.codex', 'skills'),
    'agents': os.path.join('.agents', 'skills'),
    'dsh': os.path.join('.dsh', 'skills'),
}
# WorkBuddy 的技能目录未公开固定路径，靠环境变量或 --dest 指定
ENV_OVERRIDES = {
    'workbuddy': 'WORKBUDDY_SKILLS_DIR',
    'claude': 'CLAUDE_SKILLS_DIR',
    'codex': 'CODEX_SKILLS_DIR',
    'dsh': 'DSH_SKILLS_DIR',
}

NOTES = {
    'claude': 'Claude Code：启动时自动发现，按 description 匹配',
    'codex': 'Codex：/skills 选择，或输入 $ 显式引用',
    'agents': 'Codex 与 DeepSeek Harness 共用的中立目录',
    'dsh': 'DeepSeek Harness：/doc-format-check 直接调用',
    'workbuddy': 'WorkBuddy：技能选择器；目录需用 --dest 或 WORKBUDDY_SKILLS_DIR 指定',
}


def resolve(names, project):
    """返回 [(环境名, 技能根目录或 None, 是否已存在)]。
    路径未知的环境返回 None，由调用方显式提示，不静默丢弃。"""
    out = []
    table = PROJECT_TARGETS if project else USER_TARGETS
    for name in names:
        env = ENV_OVERRIDES.get(name)
        root = os.environ.get(env) if env and not project else None
        if not root:
            root = table.get(name)
            if root and project:
                root = os.path.join(os.path.abspath(project), root)
        out.append((name, root, bool(root) and os.path.isdir(root)))
    return out


def install_one(root, link, dry):
    dest = os.path.join(root, BUNDLE_NAME)
    if os.path.realpath(dest) == os.path.realpath(BUNDLE_DIR):
        return 'skip', dest + '（就是源目录）'
    source_path = os.path.realpath(BUNDLE_DIR)
    destination_path = os.path.realpath(dest)
    try:
        common = os.path.commonpath([source_path, destination_path])
    except ValueError:
        common = None
    if common in (source_path, destination_path):
        raise ValueError('安装目录不能包含源码，也不能位于源码内')
    if os.path.lexists(dest):
        raise ValueError('目标已存在；请另选目录或先明确卸载旧副本：' + dest)
    if dry:
        return 'dry', dest
    os.makedirs(root, exist_ok=True)
    if link:
        try:
            os.symlink(BUNDLE_DIR, dest, target_is_directory=True)
            return 'link', dest
        except (OSError, NotImplementedError, AttributeError):
            pass          # Windows 无权限时回退复制
    os.makedirs(dest, exist_ok=True)
    for item in BUNDLE_ITEMS:
        src = os.path.join(BUNDLE_DIR, item)
        if not os.path.exists(src):
            continue
        tgt = os.path.join(dest, item)
        if os.path.isdir(src):
            shutil.copytree(src, tgt,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        else:
            shutil.copy2(src, tgt)
    return 'copy', dest


def uninstall_one(root, dry):
    dest = os.path.join(root, BUNDLE_NAME)
    if os.path.realpath(dest) == os.path.realpath(BUNDLE_DIR):
        return 'skip', dest + '（就是源目录，不删）'
    if not os.path.exists(dest) and not os.path.islink(dest):
        return 'none', dest
    if dry:
        return 'dry', dest
    if os.path.islink(dest):
        os.unlink(dest)
    else:
        shutil.rmtree(dest)
    return 'removed', dest


def preflight():
    """装之前先验 bundle 满足四者的最严交集。"""
    problems = []
    required = ['scripts/check_format.py', 'scripts/install.py', 'scripts/spacing.py',
                'scripts/unicode_adapter.py', 'scripts/unicode_spacing_data.py',
                'scripts/unicode_category_data.py', 'profiles/generic.json',
                'references/rules.md', 'references/spacing.md',
                'licenses/uniseg-MIT.txt', 'licenses/Unicode.txt', 'licenses/README.md']
    for relative in required:
        if not Path(BUNDLE_DIR, relative).is_file():
            problems.append('缺少必需文件：' + relative)
    for item in BUNDLE_ITEMS:
        if not os.path.exists(os.path.join(BUNDLE_DIR, item)):
            problems.append('缺少必需资源：' + item)
    try:
        validate_resources()
    except (OSError, ValueError) as exc:
        problems.append(str(exc))
    skill = os.path.join(BUNDLE_DIR, 'SKILL.md')
    if not os.path.isfile(skill):
        problems.append('缺少 SKILL.md')
        return problems

    import re
    text = open(skill, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        problems.append('SKILL.md 缺少 YAML frontmatter')
        return problems
    fm = m.group(1)
    name = re.search(r'^name:\s*(\S+)', fm, re.M)
    desc = re.search(r'^description:\s*(\S)', fm, re.M)
    if not name:
        problems.append('frontmatter 缺 name')
    if not desc:
        problems.append('frontmatter 缺 description')
    if name:
        n = name.group(1)
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', n):
            problems.append(f'name「{n}」不是 kebab-case（DSH 会拒绝）')
        if n != BUNDLE_NAME:
            problems.append(f'name「{n}」与目录名「{BUNDLE_NAME}」不一致（DSH 按目录名注册）')

    nested = []
    for root, _, files in os.walk(BUNDLE_DIR):
        if root == BUNDLE_DIR:
            continue
        if 'SKILL.md' in files:
            nested.append(os.path.relpath(os.path.join(root, 'SKILL.md'), BUNDLE_DIR))
    if nested:
        problems.append('存在嵌套 SKILL.md（DSH 不支持递归发现）：' + '、'.join(nested))
    return problems


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser()
    ap.add_argument('--targets', default=None,
                    help='逗号分隔：claude,codex,agents,dsh,workbuddy')
    ap.add_argument('--project', metavar='PATH', help='装进该项目的项目级技能目录')
    ap.add_argument('--dest', metavar='DIR', help='装进任意目录（WorkBuddy 等自定义位置）')
    ap.add_argument('--link', action='store_true', help='用符号链接（POSIX；失败自动回退复制）')
    ap.add_argument('--list', action='store_true', help='只探测并打印，不动文件')
    ap.add_argument('--uninstall', action='store_true', help='移除已装副本')
    args = ap.parse_args()

    problems = preflight()
    if problems:
        print('bundle 不满足多环境契约，已中止：', file=sys.stderr)
        for p in problems:
            print(f'  · {p}', file=sys.stderr)
        return 2
    print(f'bundle：{BUNDLE_DIR}')
    print('契约自检：frontmatter / kebab-case name / 目录名一致 / 无嵌套 SKILL.md —— 通过\n')

    if args.uninstall and not (args.targets or args.dest):
        ap.error('卸载须明确指定 --targets 或 --dest')
    chosen = args.targets or ('' if args.dest else 'claude,codex,agents,dsh,workbuddy')
    names = [n.strip() for n in chosen.split(',') if n.strip()]
    unknown = set(names) - set(NOTES)
    if unknown:
        ap.error('未知环境：' + ', '.join(sorted(unknown)))
    entries = resolve(names, args.project)
    if args.dest:
        entries.append(('custom', os.path.abspath(args.dest), os.path.isdir(args.dest)))

    if not entries:
        print('没有可用目标。用 --dest 指定目录，或设置对应环境变量。', file=sys.stderr)
        return 2

    dry = args.list
    for name, root, exists in entries:
        note = NOTES.get(name, '')
        if root is None:
            hint = ENV_OVERRIDES.get(name, '')
            where = f'设 {hint} 或用 --dest' if hint else '用 --dest'
            print(f'[{name:9}] 路径未知 —— {where}')
            if note:
                print(f'{"":12}{note}')
            continue
        if args.list:
            mark = '已存在' if exists else '不存在'
            print(f'[{name:9}] {root}  ({mark})')
            if note:
                print(f'{"":12}{note}')
            continue
        if not exists and not args.dest and not args.targets and not args.project:
            continue
        try:
            action, dest = (uninstall_one(root, dry) if args.uninstall
                            else install_one(root, args.link, dry))
        except (OSError, ValueError) as exc:
            print(f'[失败] {exc}', file=sys.stderr)
            return 2
        print(f'[{name:9}] {action:8} {dest}')

    if not args.list:
        print('\n装完后重启对应 harness，让它重新扫描技能目录。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
