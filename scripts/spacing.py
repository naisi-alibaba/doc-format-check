"""UTR59-r1 classification with a documented horizontal Markdown policy."""
from bisect import bisect_right
from functools import lru_cache
from typing import NamedTuple

from unicode_adapter import category, ensure_ready, iter_graphemes
from unicode_spacing_data import RANGES, DEFAULT

STARTS = tuple(row[0] for row in RANGES)
SENTENCE_PUNCTUATION = frozenset('!,.:;?')

class Insertion(NamedTuple):
    offset: int
    rule: str

@lru_cache(maxsize=4096)
def lookup_spacing(char):
    cp = ord(char)
    index = bisect_right(STARTS, cp) - 1
    return RANGES[index][2] if index >= 0 and cp <= RANGES[index][1] else DEFAULT

def classify_grapheme(cluster, language='und'):
    if any(category(c) == 'Me' for c in cluster):
        return 'O'
    value = lookup_spacing(cluster[0])
    if value == 'C':
        return 'N' if language == 'zh' else 'O'
    return value

def merge_spans(spans, length):
    merged = []
    for start, end in sorted(spans):
        if not 0 <= start <= end <= length:
            raise ValueError('Protected span outside text')
        if start == end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged

def plan_spacing(text, protected_spans=(), language='zh', num_space='always'):
    if language not in ('zh', 'non-zh', 'und') or num_space not in ('always', 'never'):
        raise ValueError('Invalid spacing policy')
    ensure_ready()
    if text.isascii():
        return []  # No W code points; do not use a BMP-only Han shortcut.
    spans = merge_spans(protected_spans, len(text))
    previous = None
    insertions = []
    span_index = 0
    for start, end, cluster in iter_graphemes(text):
        while span_index < len(spans) and spans[span_index][1] <= start:
            span_index += 1
        # Intersecting even part of a grapheme protects the whole cluster.
        if span_index < len(spans) and spans[span_index][0] < end:
            previous = None
            continue
        value = classify_grapheme(cluster, language)
        if lookup_spacing(cluster[0]) == 'C' and cluster[0] in SENTENCE_PUNCTUATION:
            value = 'O'  # Application policy, never modify the raw Unicode table.
        digit = category(cluster[0]) == 'Nd'
        if previous is not None:
            old_value, old_digit = previous
            if (old_value, value) in (('W', 'N'), ('N', 'W')):
                numeric = digit or old_digit
                if not (numeric and num_space == 'never'):
                    insertions.append(Insertion(start, 'F10' if numeric else 'F02'))
        previous = (value, digit)
    return insertions

def apply_insertions(text, insertions):
    output, cursor = [], 0
    for insertion in insertions:
        if insertion.offset < cursor or insertion.offset > len(text):
            raise ValueError('Invalid or duplicate insertion offset')
        output.extend((text[cursor:insertion.offset], ' '))
        cursor = insertion.offset
    output.append(text[cursor:])
    return ''.join(output)

def format_spacing(text, protected_spans=(), language='zh', num_space='always'):
    edits = plan_spacing(text, protected_spans, language, num_space)
    return apply_insertions(text, edits), {edit.rule for edit in edits}
