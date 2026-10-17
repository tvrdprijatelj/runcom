import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == 'nt', 'Bash uninstaller')
class UninstallTests(unittest.TestCase):
    def run_uninstall(self, folder, data_home, answer=None):
        return subprocess.run(['bash', str(ROOT / 'uninstall.sh')] + (['--yes'] if answer is None else []),
                              input=answer, text=True, capture_output=True,
                              env=dict(os.environ, RUNCOM_INSTALL_DIR=str(folder), XDG_DATA_HOME=str(data_home)))

    def test_removes_installation_and_shortcut_keeps_extra_files(self):
        with tempfile.TemporaryDirectory(prefix='runcom uninstall ') as directory:
            data = Path(directory)
            folder = data / 'runcom'
            folder.mkdir()
            for name in ('runcom.py', 'runcom', 'help.html', 'runcom-language'):
                (folder / name).write_text('app')
            (folder / 'venv').mkdir()
            (folder / 'venv/pyvenv.cfg').write_text('home = python')
            (folder / 'personal.sh').write_text('echo keep')
            (data / 'applications').mkdir()
            entry = data / 'applications/runcom.desktop'
            entry.write_text('Exec="' + str(folder / 'runcom') + '"')
            result = self.run_uninstall(folder, data)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((folder / 'runcom.py').exists())
            self.assertFalse((folder / 'venv').exists())
            self.assertFalse(entry.exists())
            self.assertEqual((folder / 'personal.sh').read_text(), 'echo keep')

    def test_decline_preserves_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'runcom'
            folder.mkdir()
            (folder / 'runcom.py').write_text('app')
            result = self.run_uninstall(folder, Path(directory), 'n\n')
            self.assertEqual(result.returncode, 0)
            self.assertTrue((folder / 'runcom.py').exists())

    def test_unknown_directory_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'help.html').write_text('keep')
            result = self.run_uninstall(folder, folder)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((folder / 'help.html').exists())

    def test_linked_installation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            folder = data / 'real'
            folder.mkdir()
            (folder / 'runcom.py').write_text('keep')
            link = data / 'link'
            link.symlink_to(folder, target_is_directory=True)
            result = self.run_uninstall(link, data)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((folder / 'runcom.py').exists())
