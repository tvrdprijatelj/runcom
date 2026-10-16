import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runcom

class ApplicationTests(unittest.TestCase):
    def app(self):
        # Exercise file and execution behavior without requiring a display server.
        app = object.__new__(runcom.App)
        app.editor = Mock()
        app._update_title = Mock()
        app._set_status = Mock()
        return app

    def test_windows_batch_has_explicit_interpreter(self):
        with patch.object(runcom, 'IS_WIN', True):
            command = runcom.App._command_for(None, Path('my script.cmd'))
        self.assertEqual(command, ['cmd.exe', '/d', '/c', 'my script.cmd'])

    @unittest.skipIf(os.name == 'nt', 'Unix execution')
    def test_shell_script_with_spaces_without_execute_permission(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'my script.sh'
            path.write_text('printf "success"\n')
            command = runcom.App._command_for(None, path)
            self.assertEqual(subprocess.check_output(command, text=True), 'success')

    @unittest.skipIf(os.name == 'nt', 'Unix execution')
    def test_python_uses_python_not_bash(self):
        command = runcom.App._command_for(None, Path('/tmp/test.py'))
        self.assertEqual(command[:2], [sys.executable, '-u'])

    def test_save_as_failure_restores_previous_file(self):
        app = self.app()
        app.current, app.folder = Path('/old/a.sh'), Path('/old')
        app.save = Mock(return_value=False)
        app.refresh_list = Mock()
        with patch.object(runcom.filedialog, 'asksaveasfilename', return_value='/new/b.sh'):
            self.assertFalse(app.save_as())
        self.assertEqual(app.current, Path('/old/a.sh'))
        self.assertEqual(app.folder, Path('/old'))

    @unittest.skipIf(os.name == 'nt', 'Unix file format')
    def test_save_python_does_not_insert_bash_shebang(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            app.current = Path(folder) / 'example.py'
            app.editor.get.return_value = 'print("hello")'
            self.assertTrue(app.save())
            self.assertEqual(app.current.read_text(), 'print("hello")\n')
            app.editor.insert.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'Unix quoting')
    def test_terminal_quotes_script_path(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'script; with spaces.sh'
            path.write_text('echo correct\n')
            result = subprocess.run(['bash', '-c', app._unix_inner(path)], input='\n', text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('correct', result.stdout)

if __name__ == '__main__':
    unittest.main()
