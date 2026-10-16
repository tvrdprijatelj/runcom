import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runcom


class ApplicationTests(unittest.TestCase):
    def app(self):
        app = object.__new__(runcom.App)
        app.editor = Mock()
        app._update_title = Mock()
        app._set_status = Mock()
        app._snapshot = None
        app._closing = False
        app.q = queue.Queue(maxsize=256)
        return app

    def test_help_uses_local_page_when_installed(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'runcom.py'
            guide = Path(folder) / 'help.html'
            guide.write_text('<h1>Help</h1>')
            with patch.object(runcom, '__file__', str(source)), patch.object(runcom.webbrowser, 'open', return_value=True) as browser:
                app.open_help()
            browser.assert_called_once_with(guide.as_uri(), new=2)

    def test_help_falls_back_to_online_for_standalone_app(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runcom, '__file__', str(Path(folder)/'runcom.py')), patch.object(runcom.webbrowser, 'open', return_value=True) as browser:
                app.open_help()
            browser.assert_called_once_with(runcom.HELP_URL, new=2)

    def test_help_reports_browser_launch_failure(self):
        app = self.app()
        with patch.object(runcom.webbrowser, 'open', return_value=False), patch.object(runcom.messagebox, 'showerror') as error:
            app.open_help()
        error.assert_called_once()
        self.assertIn('Öppna hjälpen manuellt', error.call_args[0][1])

    def test_python_template_is_python_on_both_platforms(self):
        for win in (False, True):
            with patch.object(runcom, 'IS_WIN', win):
                compile(runcom.template_for('hello.py'), 'hello.py', 'exec')
                self.assertIn('Write-Host', runcom.template_for('hello.ps1'))
                self.assertIn('@echo off', runcom.template_for('hello.cmd'))

    def test_windows_batch_has_explicit_interpreter_and_outer_quotes(self):
        path = Path('my & script.cmd').absolute()
        with patch.object(runcom, 'IS_WIN', True):
            command = runcom.script_command(path)
        self.assertIn('/d /v:off /s /c ', command)
        self.assertTrue(command.endswith('""' + str(path) + '""'))

    def test_windows_batch_rejects_percent_expansion_in_path(self):
        with patch.object(runcom, 'IS_WIN', True):
            with self.assertRaises(ValueError):
                runcom.script_command(Path('%TEMP%.cmd'))

    def test_pythonw_uses_console_python_for_child_scripts(self):
        with patch.object(runcom, 'IS_WIN', True), patch.object(runcom.sys, 'executable', '/runtime/pythonw.exe'):
            self.assertEqual(Path(runcom.python_executable()).name, 'python.exe')

    def test_powershell_missing_is_actionable(self):
        with patch.object(runcom, 'IS_WIN', True), patch.object(runcom.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'PowerShell'):
                runcom.script_command(Path('a.ps1'))

    @unittest.skipIf(os.name == 'nt', 'Unix execution')
    def test_shell_script_with_spaces_without_execute_permission(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'my script.sh'
            path.write_text('printf "success"\n')
            self.assertEqual(subprocess.check_output(runcom.script_command(path), text=True), 'success')

    @unittest.skipIf(os.name == 'nt', 'Unix execution')
    def test_shell_extension_respects_shebang(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'my script.sh'
            path.write_text('#!/usr/bin/env python3\nprint("success")\n')
            self.assertEqual(subprocess.check_output(runcom.script_command(path), text=True).strip(), 'success')

    @unittest.skipIf(os.name == 'nt', 'Unix execution')
    def test_plain_text_is_not_executed_as_a_program(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'notes.txt'
            path.write_text('notes')
            self.assertIsNone(runcom.script_command(path))

    def test_python_uses_python_unbuffered(self):
        command = runcom.script_command(Path('example.py'))
        self.assertEqual(command[:2], [runcom.python_executable(), '-u'])

    def test_save_as_failure_restores_previous_file_and_snapshot(self):
        app = self.app()
        app.current, app.folder = Path('/old/a.sh'), Path('/old')
        app._snapshot = b'old'
        app.save = Mock(return_value=False)
        app.refresh_list = Mock()
        with patch.object(runcom.filedialog, 'asksaveasfilename', return_value='/new/b.sh'):
            self.assertFalse(app.save_as())
        self.assertEqual(app.current, Path('/old/a.sh'))
        self.assertEqual(app.folder, Path('/old'))
        self.assertEqual(app._snapshot, b'old')

    def test_save_python_does_not_insert_bash_shebang(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            app.current = Path(folder) / 'example.py'
            app.editor.get.return_value = 'print("hello")'
            self.assertTrue(app.save())
            self.assertEqual(app.current.read_text(), 'print("hello")\n')
            app.editor.insert.assert_not_called()

    def test_external_edits_are_not_silently_overwritten(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            app.current = Path(folder) / 'example.py'
            app._snapshot = b'old'
            app.current.write_bytes(b'external change')
            app.editor.get.return_value = 'editor change'
            with patch.object(runcom.messagebox, 'askyesno', return_value=False):
                self.assertFalse(app.save())
            self.assertEqual(app.current.read_bytes(), b'external change')
            app.editor.edit_modified.assert_not_called()

    def test_deleted_file_requires_confirmation_to_recreate(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            app.current = Path(folder) / 'deleted.py'
            app._snapshot = b'old'
            app.editor.get.return_value = 'new'
            with patch.object(runcom.messagebox, 'askyesno', return_value=False):
                self.assertFalse(app.save())
            self.assertFalse(app.current.exists())

    @unittest.skipIf(os.name == 'nt', 'Unix quoting')
    def test_terminal_quotes_script_path(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'script; with spaces.sh'
            path.write_text('echo correct\n')
            result = subprocess.run(['bash', '-c', app._unix_inner(path)], input='\n', text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('correct', result.stdout)

    def test_environment_does_not_forward_legacy_password(self):
        app = self.app()
        with patch.dict(os.environ, {'SKRIPTSTUDIO_SUDO_PW': 'not-a-real-password'}):
            env = app._run_env()
        self.assertNotIn('SKRIPTSTUDIO_SUDO_PW', env)
        self.assertEqual(env['PYTHONIOENCODING'], 'utf-8')

    def test_reader_streams_output_without_newline(self):
        app = self.app()
        proc = subprocess.Popen([runcom.python_executable(), '-u', '-c',
                                 'import sys,time; sys.stdout.write("ready"); time.sleep(3)'], stdout=subprocess.PIPE)
        worker = threading.Thread(target=app._reader, args=(proc,), daemon=True)
        worker.start()
        try:
            kind, source, text = app.q.get(timeout=2)
            self.assertEqual((kind, source, text), ('line', proc, 'ready'))
        finally:
            proc.terminate()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())

    def test_full_queue_worker_can_exit_on_close(self):
        app = self.app()
        for _ in range(256):
            app.q.put(('line', None, 'data'))
        worker = threading.Thread(target=app._enqueue, args=('line', None, 'more'))
        worker.start()
        app._closing = True
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    @unittest.skipUnless(os.name == 'nt', 'Native Windows command parsing')
    def test_native_windows_batch_path_with_spaces_and_ampersand(self):
        with tempfile.TemporaryDirectory(prefix='runcom & test ') as folder:
            path = Path(folder) / 'hello & world.cmd'
            path.write_text('@echo off\necho success\n')
            result = subprocess.run(runcom.script_command(path), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'success')


class AtomicWriteTests(unittest.TestCase):
    def test_encoding_failure_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.cmd'
            path.write_bytes(b'original')
            with self.assertRaises(UnicodeEncodeError):
                runcom.atomic_write(path, '\u2603', 'ascii')
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_replace_failure_keeps_original_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.sh'
            path.write_bytes(b'original')
            with patch.object(runcom.os, 'replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    runcom.atomic_write(path, 'new', 'utf-8')
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_exclusive_create_cannot_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.py'
            path.write_bytes(b'original')
            with self.assertRaises(FileExistsError):
                runcom.atomic_write(path, 'new', 'utf-8', exclusive=True)
            self.assertEqual(path.read_bytes(), b'original')

    @unittest.skipIf(os.name == 'nt', 'Unix permissions')
    def test_existing_permissions_preserved_without_extra_group_access(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.sh'
            path.write_bytes(b'old')
            path.chmod(0o600)
            runcom.atomic_write(path, '#!/bin/sh\n', 'utf-8', executable=True)
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    @unittest.skipIf(os.name == 'nt', 'Unix symlinks')
    def test_existing_symlink_remains_a_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            target, link = Path(folder) / 'target', Path(folder) / 'link'
            target.write_bytes(b'old')
            link.symlink_to(target)
            runcom.atomic_write(link, 'new', 'utf-8')
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_bytes(), b'new')

if __name__ == '__main__':
    unittest.main()
