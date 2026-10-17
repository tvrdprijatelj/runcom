"""Verify the installed language applies without changing user file content."""
import ast
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LanguageTests(unittest.TestCase):
    def load(self, language=None):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / 'runcom.py'
            app.write_bytes((ROOT / 'runcom.py').read_bytes())
            if language is not None:
                app.with_name('runcom-language').write_text(language)
            return runpy.run_path(str(app))

    def test_installed_languages_and_templates(self):
        for lang, help_text, greeting in [('sv', 'Hjälp', 'Hej'), ('en', 'Help (Swedish)', 'Hello')]:
            app = self.load(lang)
            self.assertEqual(app['tr']('Hjälp'), help_text)
            for suffix in ('.py', '.sh', '.bat', '.ps1'):
                self.assertIn(greeting, app['template_for']('sample' + suffix))
            self.assertEqual(app['tr']('my-script.py'), 'my-script.py')

    def test_default_and_invalid_language_remain_swedish(self):
        for language in (None, 'invalid'):
            self.assertEqual(self.load(language)['LANGUAGE'], 'sv')

    def test_python38_syntax(self):
        ast.parse((ROOT / 'runcom.py').read_text(encoding='utf-8'), feature_version=(3, 8))
