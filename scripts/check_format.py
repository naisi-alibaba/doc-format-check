#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文 Markdown 格式检查器。A 档自动修，B 档只报不改。

  python3 check_format.py <文件或目录>... [--profile NAME|PATH] [--fix]
                          [--num-space always|never] [--tsv] [--report FILE]
"""

import argparse
import json
import os
import re
import sys
import tempfile
import stat
from bisect import bisect_left, bisect_right
from pathlib import Path
from collections import defaultdict

# Support both direct CLI use and importlib-based callers.
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
try:
    from spacing import format_spacing
    from unicode_adapter import ensure_ready, iter_graphemes, validate_resources, regex_class
except (ImportError, OSError, ValueError) as exc:
    if __name__ == '__main__':
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
        print('Incomplete Unicode runtime; reinstall the complete bundle: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
    raise

DIGITS = regex_class({'Nd'})
WORDS = regex_class({'Lu', 'Ll', 'Lt', 'Lm', 'Lo', 'Nd', 'Nl', 'No'}) + '_'


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(SKILL_DIR, 'profiles')

CJK = '一-鿿'                      # 汉字（不含标点、假名）
CJK_END = CJK + '）」』】》〉'      # 可作为中文句子成分结尾的字符
FULL_PUNCT = '，。！？；：、「」『』（）《》〈〉【】…—'

DEFAULTS = {
    'spacing_engine': 'utr59',
    'spacing_language': 'zh',
    'heading_level': None,        # null = 不检查分节标题层级
    'num_space': 'always',
    'quote_style': 'detect',      # detect = 只报混用
    'no_space_brands': [],
    'project_names': [],          # [{\"wrong\": [...], \"correct\": \"...\"}]
    'path_line_labels': ['前往路径', '路径', '入口'],
    'path_context': [],
    'internal_marks': ['待确认', '待补充', '待改写', '占位', 'TODO', 'TBD'],
    'rival_marks': [],
    'typo_pairs': [['登陆', '登录']],
    'typo_fix': [],               # 追加必错词
    'typo_fix_disable': [],       # 关掉内置条目
    'absolute_claims': ['绝对安全', '绝对不会', '100%', '永不', '万无一失', '完全不会'],
    'faq_heading': '常见问题',
}

TECH_NAMES = {}
for _n in ['App', 'Wi-Fi', 'GitHub', 'iPhone', 'iPad', 'iOS', 'Android', 'macOS', 'Windows',
           'Bluetooth', 'NFC', 'GPS', 'SIM', 'eSIM', 'USB', 'Type-C', 'HDMI', 'OTG', 'HDR',
           'OLED', 'LCD', 'CPU', 'GPU', 'RAM', 'ROM', 'SSD', 'HTML', 'URL', 'PDF', 'VPN',
           'DNS', 'SMS', 'VoLTE', 'VoWiFi', 'OTA', 'IMEI']:
    TECH_NAMES[_n.lower()] = _n
TECH_ALIAS = {'wifi': 'Wi-Fi', 'wi-fi': 'Wi-Fi', 'apps': 'App', 'typec': 'Type-C',
              'osx': 'macOS'}
TECH_WORD = re.compile(r'(?<![A-Za-z0-9])([A-Za-z][A-Za-z-]{1,7})(?![A-Za-z0-9])')

# F16 常见错字；字形/地区/领域偏好默认只提示，项目可显式选择统一写法。
STYLE_VARIANTS = {'帐号': '账号', '帐户': '账户', '帐单': '账单',
                  '部份': '部分', '定单': '订单', '象素': '像素', '做为': '作为',
                  '分辩': '分辨'}
BUILTIN_ZH_TYPOS = {
    '按装': '安装', '设制': '设置', '按扭': '按钮',
    '既使': '即使',
    '必须品': '必需品',
    '分辩率': '分辨率', '显视': '显示',
    '摄相头': '摄像头', '剪切板': '剪贴板', '关健': '关键',
    '辩别': '辨别',
    '迫不急待': '迫不及待', '一如继往': '一如既往',
    '再接再励': '再接再厉', '甘败下风': '甘拜下风',
}

BUILTIN_EN_TYPOS = {
    'recieve': 'receive', 'recieved': 'received', 'retreive': 'retrieve',
    'seperate': 'separate', 'seperated': 'separated', 'seperator': 'separator',
    'occured': 'occurred', 'occuring': 'occurring', 'occurance': 'occurrence',
    'occassion': 'occasion', 'definately': 'definitely', 'enviroment': 'environment',
    'sucessful': 'successful', 'succesful': 'successful', 'sucessfully': 'successfully',
    'succesfully': 'successfully', 'sucess': 'success', 'acheive': 'achieve',
    'adress': 'address', 'begining': 'beginning', 'beleive': 'believe',
    'calender': 'calendar', 'comming': 'coming', 'compatability': 'compatibility',
    'dependancy': 'dependency', 'developement': 'development', 'existance': 'existence',
    'familar': 'familiar', 'finaly': 'finally', 'functionallity': 'functionality',
    'garantee': 'guarantee', 'hight': 'height', 'independant': 'independent',
    'intergration': 'integration', 'langauge': 'language', 'lenght': 'length',
    'libary': 'library', 'maintainance': 'maintenance', 'managment': 'management',
    'neccessary': 'necessary', 'necesary': 'necessary', 'paramater': 'parameter',
    'perfomance': 'performance', 'persistant': 'persistent', 'posible': 'possible',
    'prefered': 'preferred', 'priviledge': 'privilege', 'proccess': 'process',
    'recomend': 'recommend', 'refered': 'referred', 'relevent': 'relevant',
    'responsability': 'responsibility', 'similiar': 'similar', 'threshhold': 'threshold',
    'transfered': 'transferred', 'useage': 'usage', 'usefull': 'useful',
    'widht': 'width', 'withing': 'within', 'writting': 'writing', 'yeild': 'yield',
    'thier': 'their', 'verison': 'version', 'versoin': 'version',
    'avaliable': 'available', 'availible': 'available', 'resorce': 'resource',
    'defalut': 'default', 'defualt': 'default', 'lable': 'label',
    'mannual': 'manual', 'requirment': 'requirement', 'permision': 'permission',
    'permisson': 'permission', 'buton': 'button', 'setings': 'settings',
    'sytem': 'system', 'conect': 'connect', 'conection': 'connection',
    'passowrd': 'password', 'pasword': 'password',
}


def match_case(sample, word):
    """把 word 的大小写对齐到 sample。"""
    if sample.isupper():
        return word.upper()
    if sample[:1].isupper():
        return word[:1].upper() + word[1:]
    return word

# W 不收：可能是功率也可能是「万」，交 B09。
UNITS = ['Gbps', 'Mbps', 'Kbps', 'mAh', 'nits', 'GHz', 'MHz', 'Hz', 'GB', 'MB', 'KB', 'TB',
         'fps', 'dpi', 'ppi', 'px', 'ms', 'cm', 'mm', 'kg']
UNIT_RE = re.compile(r'(?<=[' + DIGITS + r'])(?=(?:' + '|'.join(UNITS) + r')(?![A-Za-z]))')
# 例外：度数、百分比不加空格
NO_SPACE_UNIT = re.compile(r'(?<=[' + DIGITS + r'])\s+(?=[%°℃℉‰])')

DUP_PUNCT = re.compile(r'([，。！？；：、])\1+')
# 表格单元格内边距（| 两侧的空格）不算「标点旁空格」，删了会把整表挤成一团
FULL_PUNCT_SPACE_L = re.compile(r'(?<!\|)[ \t]+(?=[' + FULL_PUNCT + r'])')
FULL_PUNCT_SPACE_R = re.compile(r'(?<=[' + FULL_PUNCT + r'])[ \t]+(?!\|)')

# 左侧须为中文收尾字符，否则会改坏英文整句内的标点。
HALF2FULL = [
    (re.compile(r'(?<=[' + CJK_END + r'])\s*,\s*(?=[' + CJK + r'])'), '，'),
    (re.compile(r'(?<=[' + CJK_END + r'])\s*;\s*(?=[' + CJK + r'])'), '；'),
    (re.compile(r'(?<=[' + CJK_END + r'])\s*:\s*(?=[' + CJK + r'])'), '：'),
    (re.compile(r'(?<=[' + CJK_END + r'])\s*\?(?=\s|$|[' + CJK + r'])'), '？'),
    (re.compile(r'(?<=[' + CJK_END + r'])\s*!(?=\s|$|[' + CJK + r'])'), '！'),
    (re.compile(r'(?<=[' + CJK_END + r'])\.(?=\s|$)'), '。'),
]
HALF_PAREN = re.compile(r'(?<=[' + CJK + r'])\s*\(([^()\n]{1,40})\)')

FW_TABLE = str.maketrans({
    **{chr(0xFF10 + i): chr(0x30 + i) for i in range(10)},
    **{chr(0xFF21 + i): chr(0x41 + i) for i in range(26)},
    **{chr(0xFF41 + i): chr(0x61 + i) for i in range(26)},
    '　': ' ',
})

BAD_ABBR = re.compile(r'(?<![A-Za-z])(H5|h5|FED|Ts(?![A-Za-z])|RJS)(?![A-Za-z])')
W_AS_WAN = re.compile(r'(?<![A-Za-z0-9.])([0-9]+(?:\.[0-9]+)?)\s?[Ww](?![A-Za-z])')
BAD_SEP = re.compile(r'(?<=[' + CJK + r'])\s*(-{1,2}>?|—+|→|／|/|>)\s*(?=[' + CJK + r'])')
BOLD_LABEL = re.compile(r'^\s*\*\*[^*]+\*\*[：:]')
THEMATIC_BREAK = re.compile(r'^\s{0,3}([-*_])\s*(?:\1\s*){2,}$')

RULES = {
    'F01': ('A', '列表标记后缺空格'),
    'F02': ('A', '中英文之间缺空格'),
    'F03': ('A', '项目专名写法错误'),
    'F04': ('A', '分节标题层级不合体例'),
    'F05': ('A', '标题/列表前后缺空行'),
    'F06': ('A', '多余空白'),
    'F07': ('A', '路径分隔符不是「 > 」'),
    'F08': ('A', '路径标签被加粗'),
    'F09': ('A', '通用技术专名大小写错误'),
    'F10': ('A', '中文与数字之间缺空格'),
    'F11': ('A', '数字与单位之间缺空格'),
    'F12': ('A', '全角标点旁多余空格'),
    'F13': ('A', '标点重复使用'),
    'F14': ('A', '中文句中误用半角标点'),
    'F15': ('A', '全角数字/字母应改半角'),
    'F16': ('A', '错别字/错别单词'),

    'B01': ('B', '内部标记残留'),
    'B02': ('B', '第三方名称待裁定'),
    'B03': ('B', '普通标签被加粗'),
    'B04': ('B', '有序列表疑为并列能力'),
    'B05': ('B', '常见问题条目缺「？」'),
    'B06': ('B', '空小节（标题下无正文）'),
    'B07': ('B', '绝对化/不可核验表述'),
    'B08': ('B', '疑似错字或重复字'),
    'B09': ('B', 'W 疑似当「万」使用'),
    'B10': ('B', '同一路径在文内写法不一致'),
    'B11': ('B', 'H1 主标题缺失或重复'),
    'B12': ('B', '不地道的缩写'),
    'B13': ('B', '引号风格混用'),
}


def validate_profile(data):
    if not isinstance(data, dict):
        raise ValueError('profile 必须是 JSON 对象')
    level = data.get('heading_level')
    if level is not None and (type(level) is not int or not 2 <= level <= 6):
        raise ValueError('heading_level 必须为 null 或 2—6 的整数')
    for key, allowed in [('spacing_engine', ('utr59', 'legacy')), ('spacing_language', ('zh', 'non-zh', 'und')), ('num_space', ('always', 'never')), ('quote_style', ('detect', 'ignore', 'none'))]:
        if key in data and data[key] not in allowed:
            raise ValueError(f'{key} 可选值：{allowed}')
    if 'name' in data and (not isinstance(data['name'], str) or not data['name']):
        raise ValueError('profile name 必须为非空字符串')
    if 'faq_heading' in data and data['faq_heading'] is not None and not isinstance(data['faq_heading'], str):
        raise ValueError('faq_heading 必须是字符串或 null')
    for key in ('no_space_brands', 'path_context', 'path_line_labels', 'internal_marks',
                'rival_marks', 'absolute_claims', 'typo_fix_disable'):
        if key in data and (not isinstance(data[key], list)
                            or any(not isinstance(x, str) or not x for x in data[key])):
            raise ValueError(f'{key} 必须是非空字符串组成的数组')
    for key in ('typo_fix', 'typo_pairs'):
        if key in data and (not isinstance(data[key], list) or any(
                not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(not isinstance(x, str) or not x for x in pair) for pair in data[key])):
            raise ValueError(f'{key} 必须由两个非空字符串的词对组成')
    if 'project_names' in data:
        if not isinstance(data['project_names'], list):
            raise ValueError('project_names 必须是数组')
        for entry in data['project_names']:
            if (not isinstance(entry, dict) or not isinstance(entry.get('correct'), str)
                    or not entry['correct'] or not isinstance(entry.get('wrong'), list)
                    or any(not isinstance(x, str) or not x for x in entry['wrong'])):
                raise ValueError('project_names 的 correct 必须为非空字符串，wrong 为字符串数组')


class Profile:
    """项目私有规则，全部从 JSON 挂进来。"""

    def __init__(self, data=None):
        validate_profile({} if data is None else data)
        cfg = dict(DEFAULTS)
        cfg.update(data or {})
        self.name = cfg.get('name', 'generic')
        self.spacing_engine = cfg['spacing_engine']
        self.spacing_language = cfg['spacing_language']
        self.heading_level = cfg['heading_level']
        self.num_space = cfg['num_space']
        self.quote_style = cfg['quote_style']
        self.faq_heading = cfg['faq_heading']
        self.no_space_brands = cfg['no_space_brands']
        self.path_context = cfg['path_context']
        self.path_line_labels = cfg['path_line_labels']

        self.name_fixes = []
        for entry in cfg['project_names']:
            correct = entry['correct']
            for wrong in entry['wrong']:
                flags = re.I if re.fullmatch(r'[\x00-\x7F]+', wrong) else 0
                pat = re.escape(wrong)
                if flags:
                    pat = r'(?<![A-Za-z0-9])' + pat + r'(?![A-Za-z0-9])'
                self.name_fixes.append((re.compile(pat, flags), correct))
            self.name_fixes.sort(key=lambda p: -len(p[0].pattern))

        def _any(words):
            return re.compile('|'.join(re.escape(w) for w in words)) if words else None

        self.internal_marks = _any(cfg['internal_marks'])
        self.rival_marks = _any(cfg['rival_marks'])
        self.absolute_claims = _any(cfg['absolute_claims'])

        disabled = set(cfg['typo_fix_disable'])
        zh = {k: v for k, v in BUILTIN_ZH_TYPOS.items() if k not in disabled}
        en = {k: v for k, v in BUILTIN_EN_TYPOS.items() if k not in disabled}
        for wrong, right in cfg['typo_fix']:
            if re.fullmatch(r'[A-Za-z]+', wrong):
                en[wrong.lower()] = right
            else:
                zh[wrong] = right
        self.zh_typos, self.en_typos = zh, en
        self.zh_typo_re = (re.compile('|'.join(re.escape(k) for k in
                                               sorted(zh, key=len, reverse=True))) if zh else None)
        self.en_typo_re = (re.compile(r'(?<![A-Za-z])(' +
                                      '|'.join(sorted(en, key=len, reverse=True)) +
                                      r')(?![A-Za-z])', re.I) if en else None)

        auto = set(zh) | set(en)          # 已进 F16 的不再由 B08 重复报
        self.typo_pairs = [(re.compile(re.escape(a)), b) for a, b in list(STYLE_VARIANTS.items()) + cfg['typo_pairs']
                           if a not in auto and a.lower() not in auto]
        self.typo_pairs.append((re.compile(r'的的|了了|是是|在在|和和'), '（重复字）'))

        self.path_line = re.compile(
            r'(?:' + '|'.join(re.escape(w) for w in self.path_line_labels) + r')[：:]\s*(.+)$')

        protect = [
            r'```.*?```',                                   # 围栏代码
            r'(`+)(?!`)(.+?)(?<!`)\1(?!`)',                                   # 行内代码
            r'!\[[^\]]*\]\([^)]*\)',                        # 图片
            r'\[[^\]]*\]\([^)]*\)',                         # 链接
            r'!?\[[^\]\n]*\](?:\[[^\]\n]*\])?',  # references and conservative bracket text
            r'<!--.*?-->',
            r'&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);',
            r"""\\[!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~]""",
            r'(?<![' + WORDS + r'.+-])[' + WORDS + r'.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
            r'<[^>\n]+>',                                  # HTML / 自动链接
            r'\[\[[^\]\n]+\]\]',                       # wikilinks
            r'https?://\S+',                                # 裸 URL
            r'(?<![' + WORDS + r'])[' + WORDS + r'.-]+\.(?:com|cn|net|org|io|dev)(?:/\S*)?',   # 域名
            r'(?<![' + WORDS + r'])[' + WORDS + r'-]+\.(?:md|txt|png|jpg|jpeg|mp4|json|py|sh|html|csv|tsv)(?![' + WORDS + r'])',  # 文件名
            r'(?<![A-Za-z0-9_])[0-9]+(?:\.[0-9]+)+(?![A-Za-z0-9_])',                           # 版本号
            r'[0-9]{1,2}:[0-9]{2}',                               # 时间
        ] + [re.escape(b) for b in self.no_space_brands]
        self.protect_re = re.compile('|'.join(protect), re.S)


PROFILE_FILENAME = '.docformat.json'


def discover_profile(start):
    """从目标所在目录逐级向上找 .docformat.json。"""
    d = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start) or '.')
    while True:
        p = os.path.join(d, PROFILE_FILENAME)
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_profile(ref):
    if ref == 'generic':
        path = os.path.join(PROFILE_DIR, 'generic.json')
        if not os.path.exists(path):
            return Profile({'name': 'generic'})
    elif os.path.exists(ref):
        path = ref
    else:
        path = os.path.join(PROFILE_DIR, f'{ref}.json')
        if not os.path.exists(path):
            raise ValueError(f'找不到 profile：{ref}\n'
                             f'  查找过：{os.path.abspath(ref)}\n'
                             f'  查找过：{path}')
    with open(path, encoding='utf-8') as f:
        return Profile(json.load(f))


SENTINEL = '\x00{}\x00'


def mask(line, prof):
    store = []

    spans = [(m.start(), m.end()) for m in prof.protect_re.finditer(line)]
    if prof.spacing_engine == 'utr59' and spans and not line.isascii():
        clusters = list(iter_graphemes(line))
        starts = [a for a, _, _ in clusters]
        ends = [b for _, b, _ in clusters]
        spans = [(starts[bisect_right(ends, start)], ends[bisect_left(starts, end) - 1])
                 for start, end in spans]
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    output, cursor = [], 0
    for start, end in merged:
        output.append(line[cursor:start])
        store.append(line[start:end])
        output.append(SENTINEL.format(len(store) - 1))
        cursor = end
    output.append(line[cursor:])
    return ''.join(output), store


def unmask(line, store):
    return re.sub(r'\x00([0-9]+)\x00', lambda m: store[int(m[1])], line)


class Finding:
    def __init__(self, rule, path, line_no, snippet, suggest, detail=''):
        self.rule = rule
        self.tier, self.name = RULES[rule]
        self.path = path
        self.line_no = line_no
        self.snippet = snippet.strip()
        self.suggest = suggest
        self.detail = detail          # 词级对比，如「帐号 → 账号」


def skip_flags(lines):
    """保守保护 frontmatter、不同长度/类型围栏、缩进代码与引用定义。"""
    flags = [False] * len(lines)
    start = 0
    if lines and lines[0].strip() == '---':
        end = next((j for j in range(1, len(lines))
                    if lines[j].strip() in ('---', '...')), len(lines) - 1)
        for j in range(end + 1):
            flags[j] = True
        start = end + 1
    fence = None
    for i in range(start, len(lines)):
        line = re.sub(r'^(?: {0,3}>[ \t]?)+', '', lines[i])
        if fence:
            flags[i] = True
            if re.fullmatch(r' {0,3}' + re.escape(fence[0]) +
                            '{' + str(fence[1]) + r',}\s*', line):
                fence = None
            continue
        match = re.match(r' {0,3}(`{3,}|~{3,})(.*)$', line)
        if match and not (match[1][0] == '`' and '`' in match[2]):
            fence = (match[1][0], len(match[1]))
            flags[i] = True
        elif line.startswith(('    ', '\t')) or re.match(r' {0,3}\[[^]]+\]:', line):
            flags[i] = True
    # Across-line code spans/comments: preserve whole intersecting physical lines.
    # Already protected block content is blanked before scanning for inline spans.
    text = '\n'.join(' ' * len(line) if flags[i] else line for i, line in enumerate(lines))
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1
    pattern = re.compile(r'<!--[\s\S]*?(?:-->|$)|(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)')
    for match in pattern.finditer(text):
        if '\n' not in match.group(0):
            continue
        first = bisect_right(starts, match.start()) - 1
        last = bisect_right(starts, match.end() - 1) - 1
        for i in range(first, last + 1):
            flags[i] = True
    return flags


def fix_tech_names(text):
    def _rep(m):
        w = m.group(1)
        good = TECH_ALIAS.get(w.lower()) or TECH_NAMES.get(w.lower())
        return good if good and good != w else w
    return TECH_WORD.sub(_rep, text)


KNOWN_CROSS_WORD = re.compile(
    r'(?:决定|确定|判定|设定|指定|约定|限定|锁定|绑定|制定|选定|核定|规定)'
    r'(?:单独|单位|单元|单个|单次|单项|单一|单价|单据|单点|单向|单列)')


def is_known_cross_word(text, start, end, term):
    if term != '定单':
        return False
    return any(m.start() <= start and end <= m.end() for m in KNOWN_CROSS_WORD.finditer(text))


def fix_typos(text, prof, log):
    """F16：替换必错词，记录词级对比。"""
    if prof.zh_typo_re:
        def _zh(m):
            if is_known_cross_word(text, m.start(), m.end(), m.group(0)):
                return m.group(0)
            right = prof.zh_typos[m.group(0)]
            log.append(f'{m.group(0)} → {right}')
            return right
        text = prof.zh_typo_re.sub(_zh, text)
    if prof.en_typo_re:
        def _en(m):
            w = m.group(1)
            right = match_case(w, prof.en_typos[w.lower()])
            log.append(f'{w} → {right}')
            return right
        text = prof.en_typo_re.sub(_en, text)
    return text


def fix_line(line, prof, num_space):
    """单行 A 档修复，返回 (新行, 命中规则, 词级对比)。

    顺序即正确性：所有「加空格」规则必须排在 F12 之前，否则不幂等。
    """
    hits, typo_log = set(), []
    masked, store = mask(line, prof)
    orig = masked

    # 分隔线不是列表，进 F01 会被拆成 "- --"
    if THEMATIC_BREAK.match(masked):
        return line, set(), []

    # F01 列表标记补空格。三条排除缺一不可：
    #   (?![-*+]) 行首 ** 是加粗、-- 是分隔线；(?!\s) 已有空格；(?![0-9]) 小数
    if re.match(r'^(\s{0,3})([-+])(?=[' + CJK + r'A-Za-z])', masked):
        masked = re.sub(r'^(\s{0,3})([-+])', r'\1\2 ', masked, count=1)
        hits.add('F01')
    if re.match(r'^(\s{0,3})([0-9]+)\.(?![0-9])(?=\S)', masked):
        masked = re.sub(r'^(\s{0,3})([0-9]+)\.', r'\1\2. ', masked, count=1)
        hits.add('F01')

    # 行首语法后的空格是语法的一部分，隔离开否则会被 F12 删掉
    pm = re.match(r'^(\s*(?:[-*+]|[0-9]+\.|>|#{1,6})\s+)', masked)
    prefix, body = (pm.group(1), masked[pm.end():]) if pm else ('', masked)

    def step(rule, new):
        nonlocal body
        if new != body:
            body = new
            hits.add(rule)

    step('F15', body.translate(FW_TABLE))
    step('F16', fix_typos(body, prof, typo_log))
    for label in prof.path_line_labels:
        step('F08', re.sub(r'\*\*(' + re.escape(label) + r'[：:][^*]*)\*\*', r'\1', body))
        step('F08', re.sub(r'\*\*(' + re.escape(label) + r')\*\*', r'\1', body))
    for pat, good in prof.name_fixes:
        step('F03', pat.sub(lambda mm, g=good: mm.group(0) if mm.group(0) == g else g, body))
    step('F09', fix_tech_names(body))

    if prof.path_line.search(body):
        head, sep, tail = body.partition('：')
        if sep:
            step('F07', head + sep + BAD_SEP.sub(' > ', tail))

    def _bracket(mm):
        inner = mm.group(1)
        if '>' in inner or any(w in inner for w in prof.path_context):
            return '「' + BAD_SEP.sub(' > ', inner) + '」'
        return mm.group(0)
    step('F07', re.sub(r'「([^」]*)」', _bracket, body))

    # 标点类与加空格类：必须早于 F12
    for pat, good in HALF2FULL:
        step('F14', pat.sub(good, body))
    step('F14', HALF_PAREN.sub(lambda mm: '（' + mm.group(1) + '）', body))
    step('F13', DUP_PUNCT.sub(r'\1', body))

    if prof.spacing_engine == 'legacy':
        step('F02', re.sub(r'([' + CJK + r'])([A-Za-z])', r'\1 \2', body))
        step('F02', re.sub(r'([A-Za-z])([' + CJK + r'])', r'\1 \2', body))
        if num_space == 'always':
            step('F10', re.sub(r'([' + CJK + r'])(?=[' + DIGITS + r'])', r'\1 ', body))
            step('F10', re.sub(r'([' + DIGITS + r'])(?=[' + CJK + r'])', r'\1 ', body))
    else:
        # Mask tokens and Markdown emphasis delimiters are opaque barriers.
        barriers = [(m.start(), m.end()) for m in re.finditer(r'\x00[0-9]+\x00|\*+|_+|~{2,}', body)]
        barriers += [(m.start(), m.end()) for m in prof.protect_re.finditer(body)]
        body, spacing_hits = format_spacing(body, barriers, prof.spacing_language, num_space)
        hits.update(spacing_hits)
    step('F11', UNIT_RE.sub(' ', body))
    step('F11', NO_SPACE_UNIT.sub('', body))

    # F12 收尾：删掉上面在标点边上留下的空格
    step('F12', FULL_PUNCT_SPACE_L.sub('', body))
    step('F12', FULL_PUNCT_SPACE_R.sub('', body))
    step('F06', re.sub(r'[ \t]{2,}', ' ', body).rstrip())

    masked = prefix + body
    if masked == orig:
        return line, set(), []
    fixed = unmask(masked, store)
    if line.endswith('  ') and line.strip():
        fixed += '  '  # 两个行尾空格是 Markdown 硬换行
    if fixed == line:
        return line, set(), []
    return fixed, hits, typo_log


def fix_blank_lines(out, flags, findings, path):
    """F05：标题前后与列表块前留空行。"""
    res, prev_is_head = [], False
    for i, ln in enumerate(out):
        skip = flags[i]
        is_head = bool(re.match(r'^#{1,6}\s', ln)) and not skip
        is_list = bool(re.match(r'^\s*(?:[-*+]|[0-9]+\.)\s', ln)) and not skip
        prev = res[-1] if res else None
        prev_blank = (prev is None) or (prev.strip() == '')
        prev_list = bool(prev and re.match(r'^\s*(?:[-*+]|[0-9]+\.)\s', prev))

        if is_head and not prev_blank and res:
            res.append('')
            findings.append(Finding('F05', path, i + 1, ln, '标题前补空行'))
        if is_list and not prev_blank and not prev_list:
            res.append('')
            findings.append(Finding('F05', path, i + 1, ln, '列表块前补空行'))
        # prev_is_head 已排除围栏内的 # 注释，否则会把代码块里的注释当标题
        if prev_is_head and ln.strip() and not is_head and not skip:
            res.append('')
            findings.append(Finding('F05', path, i + 1, ln, '标题后补空行'))
        res.append(ln)
        prev_is_head = is_head
    return res


def decode_source(data):
    encoding = 'utf-8-sig' if data.startswith(b'\xef\xbb\xbf') else 'utf-8'
    raw = data.decode(encoding)
    remainder = raw.replace('\r\n', '')
    if ('\r\n' in raw and '\n' in remainder) or '\r' in remainder:
        raise ValueError('不处理混合换行或单独 CR 的文件，请先明确换行规范')
    return raw, encoding, '\r\n' if '\r\n' in raw else '\n'


def scan_file(path, prof, do_fix, num_space):
    source_bytes = Path(path).read_bytes()
    raw, encoding, newline = decode_source(source_bytes)
    lines = raw.replace('\r\n', '\n').split('\n')
    flags = skip_flags(lines)
    findings, out = [], list(lines)

    for i, ln in enumerate(lines):
        if flags[i]:
            continue
        new, hits, typo_log = fix_line(ln, prof, num_space)
        if hits:
            for r in sorted(hits):
                findings.append(Finding(r, path, i + 1, ln, new.strip(),
                                        '；'.join(typo_log) if r == 'F16' else ''))
            out[i] = new

        # B 档跑原始行，避免 A 档改动干扰语义判断
        masked, _ = mask(ln, prof)
        for pat, rule, tip in (
            (prof.internal_marks, 'B01', '待判断标记；PRD/内部草稿中可保留，按文档用途核定，不自动删除'),
            (prof.rival_marks, 'B02', '第三方名称，归属确认前不要替换'),
            (prof.absolute_claims, 'B07', '对外承诺类表述，需确认可核验'),
        ):
            if not pat:
                continue
            m = pat.search(masked)
            if m:
                findings.append(Finding(rule, path, i + 1, ln, f'命中「{m.group(0)}」：{tip}'))
        for pat, good in prof.typo_pairs:
            m = next((match for match in pat.finditer(masked)
                      if not is_known_cross_word(masked, match.start(), match.end(), match.group(0))), None)
            if m:
                findings.append(Finding('B08', path, i + 1, ln, f'「{m.group(0)}」疑应为「{good}」'))
        m = W_AS_WAN.search(masked)
        if m:
            findings.append(Finding('B09', path, i + 1, ln,
                                    f'「{m.group(0)}」若表「万」需改写；若是功率/型号则保留'))
        m = BAD_ABBR.search(masked)
        if m:
            findings.append(Finding('B12', path, i + 1, ln, f'「{m.group(0)}」是不地道缩写，确认全称'))
        if BOLD_LABEL.match(masked):
            findings.append(Finding('B03', path, i + 1, ln, '普通标签不加粗，确认后去掉 **'))

    h1 = [i for i, l in enumerate(lines) if re.match(r'^#\s', l) and not flags[i]]
    if len(h1) != 1:
        findings.append(Finding('B11', path, (h1[1] + 1) if len(h1) > 1 else 1,
                                f'H1 共 {len(h1)} 个',
                                '每个正文文件应有且只有一个 H1。标题文本要人定，脚本不代填'))
    if prof.heading_level:
        for i, l in enumerate(lines):
            if flags[i]:
                continue
            m = re.match(r'^(#{2,6})\s', l)
            if m and len(m.group(1)) != prof.heading_level:
                out[i] = '#' * prof.heading_level + out[i][len(m.group(1)):]
                findings.append(Finding('F04', path, i + 1, l, out[i]))

    out = fix_blank_lines(out, flags, findings, path)

    if out and not out[0].strip():
        n = 0
        while n < len(out) and not out[n].strip():
            n += 1
        findings.append(Finding('F06', path, 1, '（文件开头）', f'删掉开头 {n} 个空行'))
        out = out[n:]

    heads = [(i, l) for i, l in enumerate(lines) if re.match(r'^#{1,6}\s', l) and not flags[i]]
    for idx, (i, l) in enumerate(heads):
        level = len(l) - len(l.lstrip('#'))
        end = next((position for position, heading in heads[idx + 1:]
                    if len(heading) - len(heading.lstrip('#')) <= level), len(lines))
        if not any(s.strip() and not re.match(r'^#{1,6}\s', s) for s in lines[i + 1:end]):
            findings.append(Finding('B06', path, i + 1, l, '标题下无正文，确认是补内容还是删标题'))
        if prof.faq_heading and prof.faq_heading in l:
            direct_end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
            for j in range(i + 1, direct_end):
                if re.match(r'^\s*[-*+]\s', lines[j]) and '？' not in lines[j] and '?' not in lines[j]:
                    findings.append(Finding('B05', path, j + 1, lines[j], '条目应为「Q？A」形式'))

    i = 0
    while i < len(lines):
        if flags[i] or not re.match(r'^\s*[0-9]+\.\s', lines[i]):
            i += 1
            continue
        j = i
        while j < len(lines) and (re.match(r'^\s*[0-9]+\.\s', lines[j]) or not lines[j].strip()):
            j += 1
        block = [l for l in lines[i:j] if l.strip()]
        labeled = [l for l in block if re.match(r'^\s*[0-9]+\.\s*[^：:，。]{2,12}[：:]', l)]
        if len(labeled) >= 2:
            findings.append(Finding('B04', path, i + 1, block[0],
                                    f'该有序列表 {len(block)} 条中有 {len(labeled)} 条是「标签：说明」式，'
                                    '像并列能力而非顺序步骤；确认后改无序列表'))
        i = j

    if prof.quote_style == 'detect':
        body = '\n'.join(l for i, l in enumerate(lines) if not flags[i])
        corner, curly = len(re.findall(r'「', body)), len(re.findall(r'[“”]', body))
        if corner and curly:
            findings.append(Finding('B13', path, 0, f'「」×{corner}　“”×{curly}',
                                    '同文件两种引号并存，按项目风格统一'))

    paths = defaultdict(set)
    for i, l in enumerate(lines):
        if flags[i]:
            continue
        m = prof.path_line.search(l)
        if not m:
            m = re.search(r'「([^」]*>[^」]*)」', l)
        if m:
            val = m.group(1).strip()
            paths[val.split('>')[-1].strip()].add(val)
    for tail, variants in paths.items():
        if len(variants) > 1:
            findings.append(Finding('B10', path, 0, f'末级菜单「{tail}」',
                                    '文内出现多种写法：' + ' / '.join(sorted(variants))))

    new_raw = newline.join(out)
    if do_fix and new_raw != raw:
        atomic_write(path, new_raw.encode(encoding))
    return findings


def atomic_write(path, data):
    """同目录临时文件替换；逐文件原子写入，并非整批事务。"""
    target = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + target.name + '.', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        if target.exists():
            os.chmod(temporary, target.stat().st_mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.chmod(temporary, stat.S_IWRITE | stat.S_IREAD)
            os.unlink(temporary)


def is_reparse(path):
    """Junction/reparse detection also works on Python 3.10/3.11."""
    try:
        attrs = getattr(Path(path).lstat(), 'st_file_attributes', 0)
        return Path(path).is_symlink() or bool(attrs & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
    except FileNotFoundError:
        return False


def collect(targets):
    files = {}
    excluded = {'.git', '.venv', 'node_modules', '__pycache__'}
    for value in targets:
        target = Path(value)
        if is_reparse(target) or any(is_reparse(parent) for parent in target.absolute().parents):
            raise ValueError(f'不处理符号链接：{target}')
        if target.is_dir():
            scan_root = target.resolve()
            for root, dirs, names in os.walk(target):
                dirs[:] = sorted(d for d in dirs if d not in excluded
                                  and not is_reparse(Path(root, d))
                                  and scan_root in Path(root, d).resolve().parents)
                for name in sorted(names):
                    child = Path(root, name)
                    if (child.suffix.lower() == '.md' and not is_reparse(child)
                            and scan_root in child.resolve().parents):
                        files[str(child.resolve())] = str(child)
        elif target.is_file() and target.suffix.lower() == '.md':
            files[str(target.resolve())] = str(target)
        else:
            raise ValueError(f'不是有效的 Markdown 文件或目录：{target}')
    return list(files.values())


def validate_report(report, targets):
    if is_reparse(Path(report)):
        raise ValueError('报告不能使用符号链接或 reparse point')
    path = Path(report).resolve()
    if path.exists() and not path.stat().st_mode & stat.S_IWUSR:
        raise ValueError('报告文件不可写，未修改正文')
    if not path.parent.is_dir() or path.is_dir():
        raise ValueError('报告父目录必须已存在，报告路径必须是文件')
    for value in targets:
        target = Path(value).resolve()
        if path == target or (target.is_dir() and target in path.parents):
            raise ValueError('报告必须位于扫描范围之外，不能覆盖输入或进入下一次扫描')
    # 在任何正文写入前确认报告目录可写，不覆盖已有报告。
    fd, probe = tempfile.mkstemp(prefix='.docformat-probe-', dir=path.parent)
    os.close(fd)
    os.unlink(probe)



def write_report(path, findings, files, prof, applied):
    """写对比记录。"""
    a = [f for f in findings if f.tier == 'A']
    b = [f for f in findings if f.tier == 'B']
    by_rule = defaultdict(int)
    for f in a:
        by_rule[f'{f.rule} {f.name}'] += 1

    L = []
    L.append('# 格式处理对比记录\n')
    L.append(f'- profile：{prof.name}')
    L.append(f'- 扫描文件：{len(files)} 个')
    L.append(f'- A 档{"已改" if applied else "可改（本次未写入）"}：{len(a)} 处')
    L.append(f'- B 档待确认：{len(b)} 处\n')

    if by_rule:
        L.append('## 按规则统计\n')
        L.append('| 规则 | 处数 |')
        L.append('| --- | --- |')
        for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1]):
            L.append(f'| {k} | {v} |')
        L.append('')

    typos = [f for f in a if f.rule == 'F16']
    if typos:
        L.append('## 错别字修正逐条对比\n')
        L.append('| # | 位置 | 改前 → 改后 | 所在句（改后） |')
        L.append('| --- | --- | --- | --- |')
        for n, f in enumerate(typos, 1):
            loc = f'{os.path.basename(f.path)}:{f.line_no}'
            sent = f.suggest.replace('|', r'\|')
            L.append(f'| {n} | {loc} | {f.detail} | {sent} |')
        L.append('')

    if a:
        L.append('## 全部 A 档改动（整行对比）\n')
        L.append('| # | 位置 | 规则 | 改前 | 改后 |')
        L.append('| --- | --- | --- | --- | --- |')
        for n, f in enumerate(a, 1):
            loc = f'{os.path.basename(f.path)}:{f.line_no}' if f.line_no else os.path.basename(f.path)
            before = f.snippet.replace('|', r'\|')
            after = f.suggest.replace('|', r'\|')
            L.append(f'| {n} | {loc} | {f.rule} | {before} | {after} |')
        L.append('')

    if b:
        L.append('## B 档待确认（脚本未改）\n')
        for n, f in enumerate(b, 1):
            loc = f'{os.path.basename(f.path)}:{f.line_no}' if f.line_no else os.path.basename(f.path)
            L.append(f'{n}. **[{f.rule} {f.name}] {loc}**')
            L.append(f'   - 原文：{f.snippet}')
            L.append(f'   - 建议：{f.suggest}')
        L.append('')

    atomic_write(path, '\n'.join(L).encode('utf-8'))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser()
    ap.add_argument('targets', nargs='+')
    ap.add_argument('--profile', default=None,
                    help=f'内置 profile 名，或指向 JSON 的路径。'
                         f'省略时自动向上查找 {PROFILE_FILENAME}，找不到则用 generic')
    ap.add_argument('--spacing-engine', choices=['utr59', 'legacy'])
    ap.add_argument('--spacing-language', choices=['zh', 'non-zh', 'und'])
    ap.add_argument('--version', action='version', version='doc-format-check 2.0.0')
    ap.add_argument('--fix', action='store_true', help='就地应用 A 档修复（先自行备份）')
    ap.add_argument('--num-space', default=None, choices=['always', 'never'],
                    help='中文与数字之间空格；不给则用 profile 设置')
    ap.add_argument('--tsv', action='store_true', help='输出 TSV，便于贴清单')
    ap.add_argument('--report', metavar='FILE',
                    help='把改前/改后对比记录写成 Markdown 文件（放在扫描范围之外）')
    args = ap.parse_args()

    if args.fix and not args.report:
        ap.error('--fix 必须指定扫描范围外的 --report，以保留前后对比')
    try:
        validate_resources()
        ensure_ready()
        files = collect(args.targets)
        if not files:
            raise ValueError('没有可处理的 .md 文件')
        if args.report:
            validate_report(args.report, args.targets)
        jobs = []
        for p in files:
            # 整批预读，编码或配置错误在修改任何正文之前报告。
            decode_source(Path(p).read_bytes())
            if args.fix and not Path(p).stat().st_mode & stat.S_IWUSR:
                raise ValueError(f'正文不可写：{p}')
            profile_ref = args.profile or discover_profile(p) or 'generic'
            profile = load_profile(profile_ref)
            if args.spacing_engine:
                profile.spacing_engine = args.spacing_engine
            if args.spacing_language:
                profile.spacing_language = args.spacing_language
            jobs.append((p, profile, args.num_space or profile.num_space))
        all_f = []
        for p, profile, spacing in jobs:
            all_f += scan_file(p, profile, args.fix, spacing)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'[失败] {exc}', file=sys.stderr)
        return 2
    prof = Profile({'name': ' / '.join(sorted({job[1].name for job in jobs}))})
    auto = '' if args.profile else '（按各文件目录发现 profile）'
    a = [f for f in all_f if f.tier == 'A']
    b = [f for f in all_f if f.tier == 'B']
    verb = '已修' if args.fix else '可自动修'

    print(f'# 扫描 {len(files)} 个文件｜profile={prof.name}{auto}｜'
          f'A 档 {len(a)} 处（{verb}）｜B 档 {len(b)} 处（必须人确认）\n')
    for tier, group, title in (('A', a, f'A 档 · {verb}'), ('B', b, 'B 档 · 待确认，脚本未改')):
        if not group:
            continue
        print(f'## {title}')
        for n, f in enumerate(group, 1):
            loc = f'{os.path.basename(f.path)}:{f.line_no}' if f.line_no else os.path.basename(f.path)
            if args.tsv:
                print(f'{tier}{n}\t{f.rule}\t{loc}\t{f.name}\t{f.snippet}\t{f.suggest}\t{f.detail}')
            else:
                print(f'{tier}{n}. [{f.rule} {f.name}] {loc}')
                if f.detail:
                    print(f'    修正：{f.detail}')
                if tier == 'A':
                    print(f'    改前：{f.snippet}')
                    print(f'    改后：{f.suggest}')
                else:
                    print(f'    原文：{f.snippet}')
                    print(f'    建议：{f.suggest}')
        print()

    if args.report:
        try:
            write_report(args.report, all_f, files, prof, args.fix)
        except OSError as exc:
            print(f'[失败] 报告写入失败；以上控制台保留本次改动：{exc}', file=sys.stderr)
            return 2
        print(f'对比记录已写入：{args.report}')
    if args.fix:
        remaining = [finding for p, profile, spacing in jobs
                     for finding in scan_file(p, profile, False, spacing)]
        return 1 if remaining else 0
    return 1 if all_f else 0


if __name__ == '__main__':
    sys.exit(main())
