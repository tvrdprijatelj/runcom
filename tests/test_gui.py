"""Real Tk widget and process integration tests; Linux CI runs under Xvfb."""
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runcom

class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError:
            if os.environ.get('RUNCOM_REQUIRE_GUI') == '1':
                raise
            raise unittest.SkipTest('Display unavailable; CI requires real GUI tests')

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        with patch.object(runcom, 'DEFAULT_DIR', Path(self.folder.name)):
            self.app = runcom.App()
        self.errors = []
        self.app.report_callback_exception = lambda *args: self.errors.append(args)
        self.app.update()

    def tearDown(self):
        with patch.object(runcom.messagebox, 'askyesnocancel', return_value=False):
            self.app.on_close()
        self.folder.cleanup()
        self.assertEqual(self.errors, [])

    def pump_until(self, predicate, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.update()
            if predicate():
                return
            time.sleep(0.01)
        self.fail('Timed out waiting for GUI state')

    def test_settings_window_can_be_opened_reused_and_closed(self):
        self.app.btn_settings.invoke()
        self.app.update()
        window = self.app._settings_window
        self.assertTrue(window.winfo_exists())
        self.app.btn_settings.invoke()
        self.assertIs(self.app._settings_window, window)
        buttons = [child for frame in window.winfo_children() for child in frame.winfo_children()
                   if isinstance(child, tk.Button)]
        self.assertTrue(any(button['text'] == runcom.tr('Avinstallera Runcom') for button in buttons))
        if not runcom.IS_WIN:
            self.assertTrue(any(button['text'] == runcom.tr('Aktivera sudo') for button in buttons))
        window.destroy()
        self.app.btn_settings.invoke()
        self.assertTrue(self.app._settings_window.winfo_exists())

    def test_english_buttons_and_file_dialog(self):
        self.app.on_close()
        with patch.object(runcom, 'LANGUAGE', 'en'), patch.object(runcom, 'DEFAULT_DIR', Path(self.folder.name)):
            self.app = runcom.App()
            self.app.update()
            self.assertEqual(self.app.btn_run['text'], '▶ Run here (F5)')
            self.assertEqual(self.app.btn_stop['text'], '■ Stop')
            self.assertEqual(self.app.tabs.tab(self.app.terminal, 'text'), 'Terminal')
            self.assertEqual(runcom.tr('Håll sudo aktivt i sessionen'), 'Keep sudo active for this session')
            with patch.object(runcom.simpledialog, 'askstring', return_value=None) as dialog:
                self.app.new_file()
            self.assertEqual(dialog.call_args[0][0], 'New script file')

    @unittest.skipIf(os.name == 'nt', 'Unix PTY integration')
    def test_terminal_tab_runs_commands_and_restart_closes_old_shell(self):
        self.app.open_terminal()
        panel = self.app.terminal
        old = panel.session
        panel.command("printf '\\nterminal-widget-ok\\n'" )
        self.pump_until(lambda: '\nterminal-widget-ok\n' in panel.display.get('1.0', 'end'))
        panel.restart()
        self.assertIsNot(panel.session, old)
        self.assertIsNotNone(old.proc.poll())

    def test_clear_terminal_button(self):
        panel = self.app.terminal
        panel.render('terminal text')
        self.assertEqual(panel.btn_clear['text'], runcom.tr('Rensa terminalen'))
        panel.btn_clear.invoke()
        self.assertEqual(panel.display.get('1.0', 'end-1c'), '')
        self.assertEqual(panel.display.index('terminal_cursor'), '1.0')

    @unittest.skipIf(os.name == 'nt', 'Unix sudo session')
    def test_sudo_session_uses_validation_and_invalidation_without_password(self):
        fake_bin = Path(self.folder.name) / 'bin'
        fake_bin.mkdir()
        log = Path(self.folder.name) / 'sudo.log'
        fake = fake_bin / 'sudo'
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> ' + runcom.shlex.quote(str(log)) + '\n')
        fake.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(fake_bin) + os.pathsep + os.environ.get('PATH', '')}):
            self.app.open_terminal()
            panel = self.app.terminal
            panel.keep_sudo.set(True)
            panel.toggle_sudo()
            self.pump_until(lambda: log.exists() and '-v' in log.read_text())
            self.pump_until(lambda: panel.sudo_state.get() == 'Sudo: aktivt under appsessionen')
            self.pump_until(lambda: panel.session.idle())
            panel.keep_sudo.set(False)
            panel.toggle_sudo()
            self.pump_until(lambda: '-k' in log.read_text())
        self.assertFalse(panel.keep_sudo.get())
        self.assertEqual(panel.sudo_state.get(), 'Sudo: inte aktivt')

    @unittest.skipIf(os.name == 'nt', 'Unix sudo session')
    def test_startup_sudo_requests_fresh_authentication(self):
        fake_bin = Path(self.folder.name) / 'bin'
        fake_bin.mkdir()
        log = Path(self.folder.name) / 'startup-sudo.log'
        fake = fake_bin / 'sudo'
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> ' + runcom.shlex.quote(str(log)) + '\n')
        fake.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(fake_bin) + os.pathsep + os.environ.get('PATH', '')}):
            self.app.startup_sudo()
            self.pump_until(lambda: log.exists() and '-k -v' in log.read_text())
            self.pump_until(lambda: self.app.terminal.sudo_state.get() == 'Sudo: aktivt under appsessionen')
        self.assertEqual(self.app.tabs.select(), str(self.app.terminal))
        self.assertTrue(self.app.terminal.keep_sudo.get())

    @unittest.skipIf(os.name == 'nt', 'Unix sudo session')
    def test_sudo_script_uses_existing_terminal(self):
        script = Path(self.folder.name) / 'script with spaces.sh'
        script.write_text("printf '\\nsudo-script-ok\\n'\n")
        self.app.load_path(script)
        fake_bin = Path(self.folder.name) / 'bin'
        fake_bin.mkdir()
        fake = fake_bin / 'sudo'
        fake.write_text('#!/bin/sh\n[ "$1" = "--" ] && shift\nexec "$@"\n')
        fake.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(fake_bin) + os.pathsep + os.environ.get('PATH', '')}):
            self.app.open_terminal()
            original = self.app.terminal.session
            self.app.run_with_sudo()
            self.pump_until(lambda: '\nsudo-script-ok\n' in self.app.terminal.display.get('1.0', 'end'))
            self.assertIs(self.app.terminal.session, original)

    def test_help_button_and_shortcut(self):
        self.assertEqual(self.app.btn_help['text'], 'Hjälp')
        self.assertTrue(self.app.bind('<F1>'))
        with patch.object(runcom.webbrowser, 'open', return_value=True) as browser:
            self.app.btn_help.invoke()
        browser.assert_called_once()
        self.assertTrue(browser.call_args[0][0].endswith('help.html'))

    def test_create_save_search_and_open(self):
        with patch.object(runcom.simpledialog, 'askstring', return_value='hello.py'):
            self.app.new_file()
        self.assertEqual(self.app.current.name, 'hello.py')
        compile(self.app.editor.get('1.0', 'end-1c'), 'hello.py', 'exec')
        self.app.editor.insert('end', '# changed\n')
        self.app.update()
        self.assertTrue(self.app._dirty())
        self.assertTrue(self.app.save())
        self.assertFalse(self.app._dirty())
        self.app.search.set('HELLO')
        self.assertEqual(len(self.app.files), 1)
        self.app.search.set('not present')
        self.assertEqual(self.app.files, [])
        self.app.search.set('')
        self.assertEqual(len(self.app.files), 1)

    def test_run_python_displays_unicode_and_exit_code(self):
        path = Path(self.folder.name) / 'hello world.py'
        path.write_text('print("Hej åäö 🌍")\n', encoding='utf-8')
        self.app.load_path(path)
        self.app.run_in_app()
        self.pump_until(lambda: self.app.proc is None)
        text = self.app.output.get('1.0', 'end')
        self.assertIn('Hej åäö 🌍', text)
        self.assertIn('kod 0', text)
        self.assertEqual(str(self.app.btn_run['state']), 'normal')
        self.assertEqual(str(self.app.btn_stop['state']), 'disabled')

    def test_run_selected_opens_file_and_shows_output(self):
        path = Path(self.folder.name) / 'selected file.py'
        path.write_text('print("selected-run-ok")\n')
        self.app.refresh_list()
        self.app.listbox.selection_set(self.app.files.index(path))
        self.app.open_terminal()
        self.app.btn_run_selected.invoke()
        self.pump_until(lambda: self.app.proc is None)
        self.assertEqual(self.app.current, path)
        self.assertEqual(self.app.tabs.select(), self.app.tabs.tabs()[0])
        self.assertIn('selected-run-ok', self.app.output.get('1.0', 'end'))

    def test_open_and_run_file_picker(self):
        path = Path(self.folder.name) / 'picked.py'
        path.write_text('print("picked-run-ok")\n')
        with patch.object(runcom.filedialog, 'askopenfilename', return_value=str(path)):
            self.app.btn_open_run.invoke()
        self.pump_until(lambda: self.app.proc is None)
        self.assertIn('picked-run-ok', self.app.output.get('1.0', 'end'))

    def test_quick_run_cancellation_preserves_unsaved_edits(self):
        path = Path(self.folder.name) / 'other.py'
        path.write_text('print("should not run")\n')
        self.app.editor.insert('1.0', 'unsaved edits')
        with patch.object(runcom.messagebox, 'askyesnocancel', return_value=None):
            self.app._open_and_run_path(path)
        self.assertIsNone(self.app.current)
        self.assertIsNone(self.app.proc)
        self.assertEqual(self.app.editor.get('1.0', 'end-1c'), 'unsaved edits')

    def test_stop_long_running_script(self):
        path = Path(self.folder.name) / 'wait.py'
        path.write_text('import time\nprint("ready", flush=True)\ntime.sleep(60)\n')
        self.app.load_path(path)
        self.app.run_in_app()
        self.pump_until(lambda: 'ready' in self.app.output.get('1.0', 'end'))
        self.app.stop()
        self.pump_until(lambda: self.app.proc is None)
        self.assertIn('Stoppad av användaren', self.app.output.get('1.0', 'end'))

    @unittest.skipIf(os.name == 'nt', 'Unix process groups')
    def test_stop_kills_child_that_ignores_term(self):
        path = Path(self.folder.name) / 'children.py'
        path.write_text('import subprocess,sys,time\n'
                        'child = subprocess.Popen([sys.executable,"-u","-c",'
                        '\'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("child ready",flush=True); time.sleep(60)\'])\n'
                        'time.sleep(60)\n')
        self.app.load_path(path)
        self.app.run_in_app()
        self.pump_until(lambda: 'child ready' in self.app.output.get('1.0', 'end'))
        self.app.stop()
        self.pump_until(lambda: self.app.proc is None, timeout=5)

    def test_output_limit_and_clear(self):
        self.app._out('x' * 1_100_000)
        self.assertLessEqual(len(self.app.output.get('1.0', 'end-1c')), 100_000)
        self.app.clear_output()
        self.assertEqual(self.app.output.get('1.0', 'end-1c'), '')

    def test_cancel_close_preserves_unsaved_editor(self):
        self.app.editor.insert('1.0', 'unsaved')
        with patch.object(runcom.messagebox, 'askyesnocancel', return_value=None):
            self.app.on_close()
        self.assertEqual(self.app.winfo_exists(), 1)
        self.assertFalse(self.app._closing)

    def test_horizontal_scroll_and_minimum_layout(self):
        self.app.geometry('820x540')
        self.app.update()
        self.assertGreater(self.app.editor.winfo_width(), 100)
        self.assertGreater(self.app.output.winfo_height(), 30)
        self.assertTrue(self.app.editor['xscrollcommand'])

if __name__ == '__main__':
    unittest.main()
