import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('spacing_checker', ROOT / 'scripts/check_format.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
from spacing import classify_grapheme, format_spacing, lookup_spacing

class SpacingTests(unittest.TestCase):
    def test_official_classes_and_application_punctuation(self):
        for char, value in [('中', 'W'), ('𠀀', 'W'), ('é', 'N'), ('Ω', 'N'),
                            ('%', 'C'), ('#', 'C'), (',', 'C'), ('😀', 'O'), ('①', 'O')]:
            with self.subTest(char=char): self.assertEqual(lookup_spacing(char), value)
        self.assertEqual(classify_grapheme('1\ufe0f\u20e3', 'zh'), 'O')
        self.assertEqual(classify_grapheme('#', 'und'), 'O')
        self.assertEqual(format_spacing('中文,Hello')[0], '中文,Hello')

    def test_unicode_spacing_and_idempotence(self):
        examples = [('中文AI工具', '中文 AI 工具'), ('𠀀A', '𠀀 A'), ('中文é', '中文 é'),
                    ('中文e\u0301', '中文 e\u0301'), ('收益20%增长', '收益 20% 增长'),
                    ('C#开发', 'C# 开发'), ('あA', 'あ A'), ('한A', '한 A'),
                    ('中文😀A', '中文😀A'), ('中文👩🏽\u200d💻A', '中文👩🏽\u200d💻A'),
                    ('中文1\ufe0f\u20e3A', '中文1\ufe0f\u20e3A'), ('汉字\u20ddA', '汉字\u20ddA'),
                    ('中文🇨🇳A', '中文🇨🇳A'), ('𠀀\U000E0100A', '𠀀\U000E0100 A')]
        for source, expected in examples:
            with self.subTest(source=source):
                actual, _ = format_spacing(source)
                self.assertEqual(actual, expected)
                self.assertEqual(format_spacing(actual)[0], expected)

    def test_existing_unicode_whitespace_preserved(self):
        for sep in [' ', '\u00a0', '\u2009', '\u200b', '\t', '\n', '\r\n']:
            text = '中文' + sep + 'AI'
            self.assertEqual(format_spacing(text)[0], text)

    def test_language_and_numeric_policy(self):
        for language in ['und', 'non-zh']:
            self.assertEqual(format_spacing('C#开发', language=language)[0], 'C#开发')
        self.assertEqual(format_spacing('收益20%增长', num_space='never')[0], '收益20% 增长')
        self.assertEqual(format_spacing('中文20项', num_space='never')[0], '中文20项')
        self.assertEqual(format_spacing('中文20项')[1], {'F10'})
        with self.assertRaises(ValueError): format_spacing('中文', language='auto')

    def test_protection_expands_to_whole_grapheme(self):
        text = '中e\u0301文'
        self.assertEqual(format_spacing(text, [(2, 3)])[0], text)
        self.assertEqual(format_spacing('中XYZ文', [(1, 4)])[0], '中XYZ文')

    def test_full_checker_protection_and_composition(self):
        content = ('---\ntitle: 中文AI\n---\n# 示例\n\n'
                   '中文AI和𠀀é。\n\n**中文AI**\n\n中文**AI**示例\n\n'
                   '`中文AI` [中文AI](https://example.com/a?q=中文AI)\n'
                   '邮箱 test@example.com，实体 &copy;，转义 \\#。\n'
                   '<span data-name="中文AI">中文AI</span>\n'
                   '<!-- 中文AI -->\n\n````md\n```\n中文AI\n```\n````\n\n'
                   '中文ＡＩ、收益20%增长、中文,Hello。  \n下一行。\n')
        with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='.test-spacing-') as tmp:
            p = Path(tmp) / 'fixture.md';p.write_text(content, encoding='utf-8')
            checker.scan_file(str(p), checker.Profile(), True, 'always')
            result = p.read_text(encoding='utf-8')
            for protected in ['title: 中文AI', '`中文AI`', '[中文AI](https://example.com/a?q=中文AI)',
                              '**中文 AI**', '中文**AI**示例', 'test@example.com', '&copy;', '\\#',
                              '<span data-name="中文AI">', '<!-- 中文AI -->', '```\n中文AI\n```']:
                self.assertIn(protected, result)
            self.assertIn('中文 AI、收益 20% 增长、中文,Hello。  \n', result)
            before = p.read_bytes()
            checker.scan_file(str(p), checker.Profile(), True, 'always')
            self.assertEqual(p.read_bytes(), before)

    def test_known_cross_word_and_explicit_profile(self):
        examples = [('由业务决定单独退出。', '由业务决定单独退出。', False),
                    ('请确定单位和指定单元。', '请确定单位和指定单元。', False),
                    ('请核对定单。', '请核对订单。', True),
                    ('决定单独处理，再核对定单。', '决定单独处理，再核对订单。', True),
                    ('定单有误，由业务决定单独处理。', '订单有误，由业务决定单独处理。', True),
                    ('请确定定单编号。', '请确定订单编号。', True)]
        with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='.test-words-') as tmp:
            for source, expected, reported in examples:
                p = Path(tmp) / 'fixture.md';p.write_text('# 示例\n\n' + source, encoding='utf-8')
                found = checker.scan_file(str(p), checker.Profile(), False, 'always')
                self.assertEqual(any(f.rule == 'B08' for f in found), reported, source)
                checker.scan_file(str(p), checker.Profile({'typo_fix': [['定单', '订单']]}), True, 'always')
                self.assertTrue(p.read_text(encoding='utf-8').endswith(expected))

    def test_legacy_selects_only_legacy_spacing(self):
        prof = checker.Profile({'spacing_engine': 'legacy'})
        self.assertEqual(checker.fix_line('中文é', prof, 'always')[0], '中文é')
        self.assertEqual(checker.fix_line('中文é', checker.Profile(), 'always')[0], '中文 é')

    def test_invalid_new_profile_fields(self):
        for field, value in [('spacing_engine', 'auto'), ('spacing_language', True)]:
            with self.assertRaises(ValueError): checker.Profile({field: value})


class ReviewRegressionTests(unittest.TestCase):
    def check_document(self, content, expected, profile=None):
        with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='.test-review-') as tmp:
            p = Path(tmp) / 'fixture.md'
            p.write_text('# 示例\n\n' + content, encoding='utf-8')
            checker.scan_file(str(p), checker.Profile(profile), True, (profile or {}).get('num_space', 'always'))
            self.assertEqual(p.read_text(encoding='utf-8'), '# 示例\n\n' + expected)
            before = p.read_bytes()
            checker.scan_file(str(p), checker.Profile(profile), True, (profile or {}).get('num_space', 'always'))
            self.assertEqual(p.read_bytes(), before)

    def test_unicode16_digit_is_independent_of_python_unicode(self):
        from unicode_adapter import category
        digit = '\U00010D40'
        self.assertEqual(category(digit), 'Nd')
        self.check_document('中文' + digit + '项', '中文' + digit + '项', {'num_space':'never'})
        self.check_document(digit + 'kg', digit + ' kg')

    def test_reference_links_keep_labels(self):
        for use in ['[𠀀é][]', '[𠀀é]', '![𠀀é][]', '[说明][𠀀é]']:
            text = use + '\n\n[𠀀é]: ./target.md\n'
            self.check_document(text, text)

    def test_multiline_protected_regions_and_quoted_fences(self):
        for body in ['`𠀀é\nx`', '<!--\n𠀀é\n-->', '> ```\n> 𠀀é\n> ```',
                     'prefix `𠀀é\nx` suffix', '<!--\n𠀀é']:
            self.check_document(body, body)

    def test_fullwidth_typo_fixed_in_one_pass(self):
        self.check_document('中文ｒｅｃｉｅｖｅ', '中文 receive')

    def test_many_code_spans_remain_intact(self):
        body = ' '.join(['`code`'] * 2000)
        self.check_document(body, body)
