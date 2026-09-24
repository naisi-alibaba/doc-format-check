from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class CliEncodingTests(unittest.TestCase):
    def call(self, script, *args, encoding='ascii'):
        env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8='0', PYTHONDONTWRITEBYTECODE='1')
        p = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, env=env)
        p.stdout.decode('utf-8');p.stderr.decode('utf-8')
        self.assertNotIn(b'UnicodeEncodeError', p.stderr)
        return p

    def test_encoding_matrix_exit_and_disk_state(self):
        for encoding in ['ascii', 'cp936', 'cp1252', 'utf-8']:
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='.test-encoding-') as tmp:
                dest = Path(tmp) / '技能 📁'
                p = self.call(ROOT / 'scripts/install.py', '--dest', dest, encoding=encoding)
                self.assertEqual(p.returncode, 0, p.stderr)
                installed = dest / 'doc-format-check'
                for rel in ['VERSION','licenses/Unicode.txt','scripts/_vendor/uniseg-0.10.0-py3-none-any.whl','data/unicode/manifest.json']:
                    self.assertTrue((installed / rel).is_file(), rel)
                sentinel = installed / 'local.txt';sentinel.write_text('preserve')
                self.assertEqual(self.call(ROOT / 'scripts/install.py', '--dest', dest, encoding=encoding).returncode, 2)
                self.assertEqual(sentinel.read_text(), 'preserve')
                doc = Path(tmp) / '中文 📝.md';doc.write_text('# 示例\n\n𠀀é按装。\n', encoding='utf-8')
                before = doc.read_bytes();checker = installed / 'scripts/check_format.py'
                self.assertEqual(self.call(checker, doc, encoding=encoding).returncode, 1)
                self.assertEqual(doc.read_bytes(), before)
                report = Path(tmp) / '报告 📋.md'
                result = self.call(checker, doc, '--fix', '--report', report, encoding=encoding)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('𠀀 é 安装。', doc.read_text(encoding='utf-8'))
                self.assertTrue(report.is_file())
                self.assertEqual(self.call(checker, Path(tmp)/'不存在 📁.md', encoding=encoding).returncode, 2)

    def test_missing_vendor_fails_before_batch_changes(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='.test-incomplete-') as tmp:
            copied = Path(tmp) / 'doc-format-check'
            copied.mkdir()
            for folder in ['scripts','data']:
                shutil.copytree(ROOT/folder,copied/folder,ignore=shutil.ignore_patterns('__pycache__'))
            wheel = copied/'scripts/_vendor/uniseg-0.10.0-py3-none-any.whl'
            wheel.unlink()
            doc=Path(tmp)/'input.md';doc.write_text('# 示例\n中文AI\n',encoding='utf-8');before=doc.read_bytes()
            p=self.call(copied/'scripts/check_format.py',doc,'--fix','--report',Path(tmp)/'report.md')
            self.assertEqual(p.returncode,2,p.stderr)
            self.assertEqual(doc.read_bytes(),before)

    def test_cli_overrides_profile_without_combining_engines(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent,prefix='.test-policy-') as tmp:
            p=Path(tmp)/'input.md';p.write_text('# 示例\n\n中文é\n',encoding='utf-8')
            (Path(tmp)/'.docformat.json').write_text('{"spacing_engine":"legacy"}',encoding='utf-8')
            script=ROOT/'scripts/check_format.py'
            self.assertEqual(self.call(script,p).returncode,0)
            self.assertEqual(self.call(script,p,'--spacing-engine','utr59').returncode,1)
            self.assertEqual(self.call(script,p,'--profile','generic').returncode,1)


    def test_each_required_runtime_file_is_preflighted(self):
        required = ['scripts/spacing.py', 'scripts/unicode_spacing_data.py',
                    'scripts/unicode_category_data.py', 'scripts/unicode_adapter.py',
                    'licenses/Unicode.txt', 'references/spacing.md', 'profiles/generic.json']
        for missing in required:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='.test-resources-') as tmp:
                copied=Path(tmp)/'doc-format-check'
                shutil.copytree(ROOT,copied,ignore=shutil.ignore_patterns('.git','__pycache__'))
                (copied/missing).unlink()
                dest=Path(tmp)/'install'
                p=self.call(copied/'scripts/install.py','--dest',dest)
                self.assertEqual(p.returncode,2,p.stderr)
                self.assertFalse(dest.exists())
                if missing.startswith('scripts/'):
                    doc=Path(tmp)/'input.md';doc.write_text('# 示例\n\n中文AI\n',encoding='utf-8')
                    before=doc.read_bytes()
                    p=self.call(copied/'scripts/check_format.py',doc,'--fix','--report',Path(tmp)/'report.md')
                    self.assertEqual(p.returncode,2,p.stderr)
                    self.assertNotIn(b'Traceback',p.stderr)
                    self.assertEqual(doc.read_bytes(),before)

    def test_external_unicode_provider_cannot_change_results(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent,prefix='.test-provider-') as tmp:
            Path(tmp,'unicodedata2.py').write_text('raise RuntimeError("must not import external UCD")\n')
            doc=Path(tmp)/'input.md';doc.write_text('# 示例\n\n中文\U00010D40项\n',encoding='utf-8')
            env=dict(os.environ,PYTHONPATH=tmp,PYTHONIOENCODING='utf-8')
            p=subprocess.run([sys.executable,str(ROOT/'scripts/check_format.py'),str(doc),'--num-space','never'],capture_output=True,env=env)
            self.assertEqual(p.returncode,0,p.stderr)
