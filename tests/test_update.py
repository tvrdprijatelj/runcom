import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import runcom


class UpdateTests(unittest.TestCase):
    def test_automatic_updates_only_run_for_installed_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.assertFalse(runcom.automatic_updates_enabled(folder))
            (folder / 'runcom-revision').write_text('abc')
            self.assertTrue(runcom.automatic_updates_enabled(folder))
            (folder / '.git').mkdir()
            self.assertFalse(runcom.automatic_updates_enabled(folder))

    def test_available_release_is_installed_without_confirmation(self):
        release = {'revision': 'new', 'tag_name': 'v2'}
        with patch.object(runcom, 'available_release', return_value=release), \
                patch.object(runcom, 'install_release') as install:
            self.assertIs(runcom.install_available_release(Path('/installed')), release)
        install.assert_called_once_with(Path('/installed'), release)

    def test_no_install_when_current_release_is_latest(self):
        with patch.object(runcom, 'available_release', return_value=None), \
                patch.object(runcom, 'install_release') as install:
            self.assertIsNone(runcom.install_available_release(Path('/installed')))
        install.assert_not_called()

    def test_only_newer_releases_are_offered(self):
        for status in ('ahead', 'behind', 'identical', 'diverged'):
            with self.subTest(status=status), patch.object(runcom, 'current_revision', return_value='old'), patch.object(runcom, 'github_json', side_effect=[{'tag_name': 'v2'}, {'sha': 'new'}, {'status': status}]) as api:
                release = runcom.available_release(Path('.'))
                self.assertEqual(bool(release), status == 'ahead')
                self.assertIn('old...new', api.call_args.args[0])

    def test_invalid_python_does_not_replace_existing_app(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'broken python !'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            app = folder / 'runcom.py'
            app.write_text('original')
            with patch.object(runcom.urllib.request, 'urlopen', return_value=response):
                with self.assertRaises(SyntaxError):
                    runcom.install_release(folder, {'revision': 'abc'})
            self.assertEqual(app.read_text(), 'original')

    def test_success_preserves_user_files(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'# updated'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'runcom-language').write_text('en')
            (folder / 'runcom-first-run').write_text('1\n')
            with patch.object(runcom.urllib.request, 'urlopen', return_value=response):
                runcom.install_release(folder, {'revision': 'abc'})
            self.assertEqual((folder / 'runcom.py').read_text(), '# updated')
            self.assertEqual((folder / 'runcom-revision').read_text(), 'abc')
            self.assertEqual((folder / 'runcom-language').read_text(), 'en')
            self.assertEqual((folder / 'runcom-first-run').read_text(), '1\n')
            self.assertEqual((folder / 'uninstall.sh').read_text(), '# updated')
            self.assertEqual((folder / 'uninstall.ps1').read_text(), '# updated')
