from pathlib import Path
import importlib.util
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from unicode_adapter import validate_resources, iter_graphemes, category
from unicode_spacing_data import RANGES

class UnicodeDataTests(unittest.TestCase):
    def test_assets_and_generated_table_are_exact(self):
        validate_resources()
        spec = importlib.util.spec_from_file_location('generator', ROOT / 'tools/generate_spacing_data.py')
        generator = importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
        self.assertEqual(generator.render().encode(), (ROOT / 'scripts/unicode_spacing_data.py').read_bytes())
        self.assertEqual(len(RANGES), 1299)

    def test_every_official_grapheme_fixture(self):
        count = 0
        for number, line in enumerate((ROOT / 'tests/fixtures/unicode-16/GraphemeBreakTest.txt').read_text(encoding='utf-8').splitlines(), 1):
            line = line.split('#', 1)[0].strip()
            if not line: continue
            chars, expected = [], []
            for part in line.split():
                if part == '÷': expected.append(len(chars))
                elif part != '×': chars.append(chr(int(part, 16)))
            text = ''.join(chars)
            actual = [a for a, _, _ in iter_graphemes(text)] + [len(text)]
            self.assertEqual(actual, expected, f'Unicode16 fixture line {number}')
            count += 1
        self.assertEqual(count, 1093)
        self.assertEqual(category('\u20e3'), 'Me')
