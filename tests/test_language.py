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
        for lang, help_text, greeting in [('sv', 'Hjälp', 'Hej'), ('en', 'Help', 'Hello')]:
            app = self.load(lang)
            self.assertEqual(app['tr']('Hjälp'), help_text)
            for suffix in ('.py', '.sh', '.bat', '.ps1'):
                self.assertIn(greeting, app['template_for']('sample' + suffix))
            self.assertEqual(app['tr']('my-script.py'), 'my-script.py')

    def test_default_and_invalid_language_remain_swedish(self):
        for language in (None, 'invalid'):
            self.assertEqual(self.load(language)['LANGUAGE'], 'sv')

    def test_missing_or_invalid_preference_is_detected_as_first_run(self):
        app = self.load('sv')
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'runcom-language'
            self.assertIsNone(app['language_preference'](marker))
            marker.write_text('invalid', encoding='utf-8')
            self.assertIsNone(app['language_preference'](marker))
            marker.write_text('en\n', encoding='utf-8')
            self.assertEqual(app['language_preference'](marker), 'en')

    def test_first_run_language_is_applied_before_app_creation(self):
        app = self.load('sv')
        app['activate_runtime_language']('en')
        runtime = app['activate_runtime_language'].__globals__
        self.assertEqual(runtime['LANGUAGE'], 'en')
        self.assertIn('Write your commands here', runtime['TPL_UNIX'])
        self.assertIn('Hello from', runtime['TPL_BAT'])
        self.assertIn('Hello from', runtime['TPL_PS1'])

    def test_python38_syntax(self):
        ast.parse((ROOT / 'runcom.py').read_text(encoding='utf-8'), feature_version=(3, 8))

    def test_all_literal_ui_strings_have_translations(self):
        tree = ast.parse((ROOT / 'runcom.py').read_text(encoding='utf-8'))
        translations = self.load('en')['TRANSLATIONS']
        literals = [node.args[0].value for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'tr' and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)]
        self.assertEqual([], [text for text in literals if text not in translations])

    def test_english_default_folder_preserves_legacy_scripts(self):
        choose = self.load('en')['default_scripts_dir']
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            self.assertEqual(choose('en', home), home / 'Runcom Scripts')
            legacy = home / 'skript'
            legacy.mkdir()
            self.assertEqual(choose('en', home), legacy)
            preferred = home / 'Runcom Scripts'
            preferred.mkdir()
            self.assertEqual(choose('en', home), legacy)
            self.assertEqual(choose('sv', home), legacy)
            legacy.rmdir()
            self.assertEqual(choose('sv', home), preferred)

    def test_update_errors_follow_selected_language(self):
        with tempfile.TemporaryDirectory() as folder:
            for language, expected in (
                    ('sv', 'Versionsinformation saknas.'),
                    ('en', 'Version information is missing.')):
                app = self.load(language)
                with self.assertRaisesRegex(ValueError, expected):
                    app['current_revision'](Path(folder))

    def test_language_preference_is_written_atomically(self):
        app = self.load('sv')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'runcom-language'
            app['save_language']('en', target)
            self.assertEqual(target.read_text(encoding='utf-8'), 'en\n')
            with self.assertRaises(ValueError):
                app['save_language']('de', target)
            self.assertEqual(target.read_text(encoding='utf-8'), 'en\n')

    def test_first_run_completion_has_a_separate_marker(self):
        app = self.load('en')
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'runcom-first-run'
            self.assertFalse(app['first_run_complete'](marker))
            app['mark_first_run_complete'](marker)
            self.assertTrue(app['first_run_complete'](marker))
            marker.write_text('invalid', encoding='utf-8')
            self.assertFalse(app['first_run_complete'](marker))
