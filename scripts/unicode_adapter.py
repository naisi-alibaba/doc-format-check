"""Pinned Unicode grapheme/category implementation, loaded only from our wheel."""
from functools import lru_cache
from bisect import bisect_right
from unicode_category_data import CATEGORY_RANGES
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / 'scripts/_vendor/uniseg-0.10.0-py3-none-any.whl'
WHEEL_SHA256 = 'd280cd632b75efe867aee798d66634426de31a9d29a3d79be208108e8cb45032'
CATEGORY_SHA256 = '7676ab755a41ef82108460238569e60ad65c191ddafe61b36c6765ec1353f293'
CATEGORY_STARTS = tuple(r[0] for r in CATEGORY_RANGES)

TABLE_SHA256 = 'a8d007d71872ca6a7ea54403402f9b5e0d2670bd436389656e6aab5593f3146f'

def validate_resources():
    """Check everything before a batch can modify documents; no network fallback."""
    manifest_path = ROOT / 'data/unicode/manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        expected = {
            'scripts/_vendor/uniseg-0.10.0-py3-none-any.whl': WHEEL_SHA256,
            'data/unicode/east-asian-spacing-utr59-r1.txt': TABLE_SHA256,
            'data/unicode/DerivedGeneralCategory-16.0.0.txt': CATEGORY_SHA256,
        }
        if manifest['grapheme_unicode'] != '16.0.0' or manifest['dependency'] != 'uniseg==0.10.0':
            raise ValueError('Unicode resource version mismatch')
        for relative, digest in expected.items():
            if manifest['files'].get(relative) != digest:
                raise ValueError('Unexpected resource manifest: ' + relative)
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
                raise ValueError('Unicode resource digest mismatch: ' + relative)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Unicode resources missing or invalid; reinstall the complete bundle') from exc

@lru_cache(maxsize=1)
def _load():
    validate_resources()
    prefix = str(WHEEL.resolve()).replace('\\', '/') + '/uniseg/'
    for name, module in tuple(sys.modules.items()):
        if name == 'uniseg' or name.startswith('uniseg.'):
            origin = str(getattr(module, '__file__', '')).replace('\\', '/')
            if not origin.casefold().startswith(prefix.casefold()):
                raise ValueError('Conflicting uniseg already loaded; run this CLI in a separate process')
    # zipimport uses the exact wheel; remove the search path again after all imports.
    sys.path.insert(0, str(WHEEL))
    try:
        package = importlib.import_module('uniseg')
        graphemes = importlib.import_module('uniseg.graphemecluster')
    except (ImportError, OSError) as exc:
        raise ValueError('Cannot load bundled uniseg; reinstall the complete bundle') from exc
    finally:
        sys.path.remove(str(WHEEL))
    if package.unidata_version != '16.0.0':
        raise ValueError('Unsupported grapheme Unicode version')
    return graphemes

def ensure_ready():
    _load()

def iter_graphemes(text):
    offset = 0
    for cluster in _load().grapheme_clusters(text):
        end = offset + len(cluster)
        yield offset, end, cluster
        offset = end

@lru_cache(maxsize=4096)
def category(char):
    cp = ord(char)
    index = bisect_right(CATEGORY_STARTS, cp) - 1
    return CATEGORY_RANGES[index][2] if index >= 0 and cp <= CATEGORY_RANGES[index][1] else 'Cn'


def regex_class(categories):
    """Regex range contents sourced from pinned data, independent of Python UCD."""
    parts = []
    for lo, hi, cat in CATEGORY_RANGES:
        if cat in categories:
            escape = lambda cp: ('\\u%04X' if cp <= 0xFFFF else '\\U%08X') % cp
            parts.append(escape(lo) + ('-' + escape(hi) if hi != lo else ''))
    return ''.join(parts)
