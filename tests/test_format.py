import importlib.util
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('checker', ROOT / 'scripts/check_format.py')
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class FormatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='.test-tmp-', dir=ROOT.parent)
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name).resolve()
        assert ROOT.parent in self.work.parents
        self.docs = self.work / 'docs'
        self.docs.mkdir()
        self.file = self.docs / 'sample.md'
        self.report = self.work / 'changes.md'

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/check_format.py'),
                               *map(str, args)], capture_output=True, encoding='utf-8')

    def scan(self, text, profile=None, fix=True):
        self.file.write_text(text, encoding='utf-8')
        found = checker.scan_file(str(self.file), checker.Profile(profile), fix, 'always')
        return self.file.read_text(encoding='utf-8'), found

    def test_code_links_and_hard_breaks_survive(self):
        text = '# 示例\n\n使用AI。  \n下一行。\n\n```python\nx="使用AI, 帐号"\n```\n\n~~~text\n使用AI,\n~~~\n\n[原文](https://example.org/a?x=1)\n'
        actual, _ = self.scan(text)
        self.assertIn('使用 AI。  \n下一行', actual)
        self.assertIn('x="使用AI, 帐号"', actual)
        self.assertIn('~~~text\n使用AI,\n~~~', actual)
        self.assertIn('[原文](https://example.org/a?x=1)', actual)
        again = checker.scan_file(str(self.file), checker.Profile(), True, 'always')
        self.assertFalse([f for f in again if f.tier == 'A'])

    def test_long_fence_keeps_short_fence_as_content(self):
        text = '# 示例\n\n````md\n```\n使用AI\n```\n````\n\n使用AI\n'
        actual, _ = self.scan(text)
        self.assertIn('```\n使用AI\n```', actual)
        self.assertTrue(actual.endswith('使用 AI\n'))

    def test_frontmatter_bom_and_crlf_preserved(self):
        raw = b'\xef\xbb\xbf' + '---\r\ntitle: 使用AI\r\n---\r\n# 示例\r\n\r\n使用AI\r\n'.encode()
        self.file.write_bytes(raw)
        checker.scan_file(str(self.file), checker.Profile(), True, 'always')
        actual = self.file.read_bytes()
        self.assertTrue(actual.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\n', actual.replace(b'\r\n', b''))
        self.assertIn('title: 使用AI'.encode(), actual)

    def test_style_variants_reported_not_changed(self):
        actual, found = self.scan('# 示例\n\n帐号、部份、象素、登陆。\n')
        self.assertIn('帐号、部份、象素、登陆', actual)
        self.assertTrue(any(f.rule == 'B08' for f in found))
        actual, _ = self.scan('# 示例\n\n帐号\n', {'typo_fix': [['帐号', '账号']]})
        self.assertIn('账号', actual)

    def test_negative_number_and_emphasis_preserved(self):
        actual, _ = self.scan('# 示例\n\n-10\n\n*强调*\n\n**加粗**\n')
        self.assertIn('\n-10\n', actual)
        self.assertIn('*强调*', actual)
        self.assertNotIn('* 强调*', actual)

    def test_explicit_heading_profile_actually_fixes(self):
        actual, _ = self.scan('# 示例\n\n## 小节\n\n内容。\n', {'heading_level': 3})
        self.assertIn('### 小节', actual)
        self.assertFalse([f for f in checker.scan_file(str(self.file), checker.Profile({'heading_level': 3}), False, 'always') if f.tier == 'A'])

    def test_dry_run_is_read_only_and_apply_has_report(self):
        original = '# 示例\n\n使用AI按装。\n'
        self.file.write_text(original, encoding='utf-8')
        result = self.cli(self.file)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.file.read_text(encoding='utf-8'), original)
        result = self.cli(self.file, '--fix', '--report', self.report)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('使用 AI 安装。', self.file.read_text(encoding='utf-8'))
        self.assertIn('按装 → 安装', self.report.read_text(encoding='utf-8'))
        self.assertEqual(self.cli(self.file).returncode, 0)

    def test_fix_without_report_never_writes(self):
        self.file.write_text('# 示例\n使用AI\n', encoding='utf-8')
        before = self.file.read_bytes()
        self.assertEqual(self.cli(self.file, '--fix').returncode, 2)
        self.assertEqual(self.file.read_bytes(), before)

    def test_report_cannot_overwrite_input_or_enter_scan(self):
        self.file.write_text('# 示例\n使用AI\n', encoding='utf-8')
        before = self.file.read_bytes()
        for target in [self.file, self.docs / 'report.md']:
            result = self.cli(self.docs, '--fix', '--report', target)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.file.read_bytes(), before)

    def test_invalid_batch_stops_before_modification(self):
        self.file.write_text('# 示例\n使用AI\n', encoding='utf-8')
        bad = self.docs / 'z.md'
        bad.write_bytes(b'\xff\xff')
        before = self.file.read_bytes()
        self.assertEqual(self.cli(self.docs, '--fix', '--report', self.report).returncode, 2)
        self.assertEqual(self.file.read_bytes(), before)

    def test_each_file_discovers_its_own_profile(self):
        other = self.work / 'other'
        other.mkdir()
        (self.docs / '.docformat.json').write_text(json.dumps({'typo_fix': [['测试词', '项目甲']]}), encoding='utf-8')
        (other / '.docformat.json').write_text(json.dumps({'typo_fix': [['测试词', '项目乙']]}), encoding='utf-8')
        self.file.write_text('# 示例\n\n测试词\n', encoding='utf-8')
        second = other / 'sample.md'
        second.write_text('# 示例\n\n测试词\n', encoding='utf-8')
        result = self.cli(self.file, second, '--fix', '--report', self.report)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('项目甲', self.file.read_text(encoding='utf-8'))
        self.assertIn('项目乙', second.read_text(encoding='utf-8'))

    def test_every_style_variant_is_reported_individually(self):
        for word in ['帐号', '帐户', '帐单', '部份', '定单', '象素', '做为', '分辩']:
            with self.subTest(word=word):
                actual, found = self.scan('# 示例\n\n' + word + '\n')
                self.assertIn(word, actual)
                self.assertTrue(any(f.rule == 'B08' and word in f.snippet for f in found))

    def test_parent_headings_are_not_empty_and_open_questions_remain(self):
        actual, found = self.scan('# 示例\n\n## 功能\n\n### 搜索\n\n优先级待确认。\n')
        self.assertFalse(any(f.rule == 'B06' for f in found))
        self.assertIn('待确认', actual)
        self.assertFalse(any('确认后再删' in f.suggest for f in found))

    def test_invalid_profile_aborts_entire_batch(self):
        for value in [-1, '3', True, 9]:
            self.file.write_text('# 示例\n使用AI\n', encoding='utf-8')
            other = self.work / 'bad'
            other.mkdir(exist_ok=True)
            second = other / 'sample.md'
            second.write_text('# 示例\n\n## 小节\n内容', encoding='utf-8')
            (other / '.docformat.json').write_text(json.dumps({'heading_level': value}))
            before = self.file.read_bytes()
            self.assertEqual(self.cli(self.file, second, '--fix', '--report', self.report).returncode, 2)
            self.assertEqual(self.file.read_bytes(), before)

    def test_readonly_report_aborts_before_changes(self):
        self.file.write_text('# 示例\n使用AI\n', encoding='utf-8')
        before = self.file.read_bytes()
        self.report.write_text('old')
        self.report.chmod(stat.S_IREAD)
        try:
            self.assertEqual(self.cli(self.file, '--fix', '--report', self.report).returncode, 2)
            self.assertEqual(self.file.read_bytes(), before)
            self.assertEqual(self.report.read_text(), 'old')
        finally:
            self.report.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_mixed_newlines_rejected_and_clean_bytes_unchanged(self):
        raw = '# 示例\r\n\n```\r\n代码\r\n```\r\n'.encode()
        self.file.write_bytes(raw)
        self.assertEqual(self.cli(self.file, '--fix', '--report', self.report).returncode, 2)
        self.assertEqual(self.file.read_bytes(), raw)
        clean = '# 示例\r\n\r\n内容。'.encode()
        self.file.write_bytes(clean)
        self.assertEqual(self.cli(self.file, '--fix', '--report', self.report).returncode, 0)
        self.assertEqual(self.file.read_bytes(), clean)

    def test_project_install_ignores_global_env_override(self):
        project = self.work / 'project'
        fake_global = self.work / 'global'
        env = dict(os.environ, CODEX_SKILLS_DIR=str(fake_global))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'),
                                 '--project', str(project), '--targets', 'codex'],
                                capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((project / '.codex/skills/doc-format-check/SKILL.md').is_file())
        self.assertFalse(fake_global.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction case')
    def test_junction_subdirectory_cannot_escape_scan_root(self):
        outside = self.work / 'outside'
        outside.mkdir()
        external = outside / 'external.md'
        external.write_text('# 示例\n使用AI\n', encoding='utf-8')
        before = external.read_bytes()
        junction = self.docs / 'jump'
        # One shell creates the explicitly bounded test junction; no deletion via shell.
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(outside)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            self.assertEqual(checker.collect([str(self.docs)]), [])
            with self.assertRaises(ValueError):
                checker.collect([str(junction)])
            self.assertEqual(external.read_bytes(), before)
        finally:
            os.rmdir(junction)

    def test_none_quote_style_is_backward_compatible(self):
        actual, found = self.scan('# 示例\n\n「内容」与“说明”。\n', {'quote_style': 'none'})
        self.assertFalse(any(f.rule == 'B13' for f in found))

    def test_faq_answer_lists_are_not_questions(self):
        _, found = self.scan('# 示例\n\n## 常见问题\n\n### 如何安装？\n\n- 下载应用。\n- 点击安装。\n')
        self.assertFalse(any(f.rule == 'B05' for f in found))

    def test_installer_explicit_dest_and_existing_copy(self):
        install = ROOT / 'scripts/install.py'
        result = subprocess.run([sys.executable, str(install), '--dest', str(self.work / 'skills')], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.work / 'skills/doc-format-check'
        self.assertTrue((installed / 'SKILL.md').is_file())
        sentinel = installed / 'local.txt'
        sentinel.write_text('keep')
        result = subprocess.run([sys.executable, str(install), '--dest', str(self.work / 'skills')], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(sentinel.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
