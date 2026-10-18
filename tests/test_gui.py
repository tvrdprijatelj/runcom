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

    def test_language_can_be_changed_and_restarts_app(self):
        self.app.open_settings()
        self.assertEqual(self.app.language_choice.get(), runcom.LANGUAGE)
        language_file = Path(self.folder.name) / 'runcom-language'
        source = Path(self.folder.name) / 'runcom.py'
        with patch.object(runcom, '__file__', str(source)), \
                patch.object(self.app, '_confirm_discard', return_value=True), \
                patch.object(self.app, 'on_close') as close, \
                patch.object(runcom.subprocess, 'Popen') as launch:
            self.app.language_choice.set('en' if runcom.LANGUAGE == 'sv' else 'sv')
            self.app.btn_apply_language.invoke()
        self.assertEqual(language_file.read_text(encoding='utf-8').strip(),
                         'en' if runcom.LANGUAGE == 'sv' else 'sv')
        launch.assert_called_once_with([sys.executable, str(source)], cwd=str(source.parent))
        close.assert_called_once_with(confirm=False)

    def test_language_change_rolls_back_if_restart_fails(self):
        self.app.open_settings()
        language_file = Path(self.folder.name) / 'runcom-language'
        source = Path(self.folder.name) / 'runcom.py'
        with patch.object(runcom, '__file__', str(source)), \
                patch.object(self.app, '_confirm_discard', return_value=True), \
                patch.object(runcom.subprocess, 'Popen', side_effect=OSError('restart failed')), \
                patch.object(runcom.messagebox, 'showerror') as error:
            self.app.language_choice.set('en' if runcom.LANGUAGE == 'sv' else 'sv')
            self.app.btn_apply_language.invoke()
        self.assertEqual(language_file.read_text(encoding='utf-8').strip(), runcom.LANGUAGE)
        self.assertIn('restart failed', error.call_args[0][1])

    def test_first_run_language_dialog_saves_english_choice(self):
        source = Path(self.folder.name) / 'runcom.py'

        def choose_english(window):
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            button = next(child for child in descendants(window)
                          if isinstance(child, tk.Button) and child.cget('text') == 'English')
            button.invoke()

        with patch.object(runcom, '__file__', str(source)), \
                patch.object(tk.Tk, 'mainloop', choose_english):
            self.assertEqual(runcom.choose_initial_language(), 'en')
        self.assertEqual(source.with_name('runcom-language').read_text(encoding='utf-8'), 'en\n')
        self.assertEqual(source.with_name('runcom-first-run').read_text(encoding='utf-8'), '1\n')

    def test_brand_logo_and_editor_identity_are_visible(self):
        self.assertTrue(hasattr(self.app, '_app_icon'))
        self.assertTrue(hasattr(self.app, '_header_logo'))
        self.assertEqual(self.app.logo_label.cget('image'), str(self.app._header_logo))
        self.assertEqual(self.app.file_label.cget('text'), runcom.tr('Ingen fil vald'))
        self.assertEqual(self.app.cget('background'), runcom.THEME['bg'])

    def test_english_buttons_and_file_dialog(self):
        self.app.on_close()
        with patch.object(runcom, 'LANGUAGE', 'en'), patch.object(runcom, 'DEFAULT_DIR', Path(self.folder.name)):
            self.app = runcom.App()
            self.app.update()
            self.assertEqual(self.app.btn_run['text'], '▶ Run in app (F5)')
            self.assertEqual(self.app.btn_stop['text'], '■ Stop')
            self.assertEqual(self.app.btn_edit_selected['text'], 'Edit selected script')
            self.assertEqual(self.app.tabs.tab(self.app.terminal, 'text'), 'Terminal')
            self.assertEqual(runcom.tr('Håll sudo aktivt i sessionen'), 'Keep sudo active while Runcom is open')
            self.assertEqual(runcom.tr('Kör med sudo (F8)'), 'Run with sudo (F8)')
            with patch.object(runcom.simpledialog, 'askstring', return_value=None) as dialog:
                self.app.new_file()
            self.assertEqual(dialog.call_args[0][0], 'New script file')

    def test_english_main_settings_and_sudo_dialog_have_no_swedish_ui_text(self):
        self.app.on_close()
        with patch.object(runcom, 'LANGUAGE', 'en'), patch.object(runcom, 'DEFAULT_DIR', Path(self.folder.name)):
            self.app = runcom.App()
            self.app.open_settings()
            self.app.prompt_sudo_password()
            self.app.update()
            texts = [self.app.tabs.tab(tab, 'text') for tab in self.app.tabs.tabs()]

            def collect(widget):
                try:
                    value = widget.cget('text')
                except tk.TclError:
                    value = ''
                if value and not str(value).startswith('PY_VAR'):
                    texts.append(str(value))
                for child in widget.winfo_children():
                    collect(child)

            collect(self.app)
            visible = '\n'.join(texts)
            for swedish in ('Hjälp', 'Inställningar', 'Skript', 'Kör', 'Lösenord',
                            'Rensa', 'Spara', 'Stäng', 'Ta bort', 'Välj'):
                self.assertNotIn(swedish, visible)
            self.app._sudo_password_window.destroy()
            self.app._sudo_password_window = None
            self.app._settings_window.destroy()

    @unittest.skipIf(os.name == 'nt', 'Unix PTY integration')
    def test_terminal_tab_runs_commands_and_restart_closes_old_shell(self):
        self.app.open_terminal()
        panel = self.app.terminal
        self.assertEqual(panel.display.cget('background'), '#000000')
        self.assertEqual(panel.display.cget('foreground'), runcom.THEME['terminal_text'])
        self.assertEqual(panel.display.cget('insertbackground'), runcom.THEME['terminal_text'])
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
            self.pump_until(lambda: log.exists() and '-k\n-n -v\n' in log.read_text())
            self.pump_until(lambda: self.app.terminal.sudo_state.get() == 'Sudo: aktivt under appsessionen')
        self.assertEqual(self.app.tabs.select(), self.app.tabs.tabs()[0])
        self.assertTrue(self.app.terminal.keep_sudo.get())

    def test_graphical_sudo_password_is_hidden_and_sent_to_pty(self):
        with patch.object(self.app.terminal, 'send') as send:
            self.app.prompt_sudo_password()
            window = self.app._sudo_password_window
            entry = self.app._sudo_password_entry
            self.assertEqual(entry.cget('show'), '•')
            entry.insert(0, 'graphical-test-password')
            entry.event_generate('<Return>')
            self.app.update()
        send.assert_called_once_with('graphical-test-password\n')
        self.assertIsNone(self.app._sudo_password_window)
        self.assertFalse(window.winfo_exists())

    def test_final_wrong_sudo_password_shows_graphical_error(self):
        self.app._sudo_password_attempted = True
        with patch.object(runcom.messagebox, 'showerror') as error:
            self.app.sudo_password_rejected()
        error.assert_called_once_with(runcom.tr('Fel sudo-lösenord'),
                                      runcom.tr('Sudo-lösenordet kunde inte verifieras.'),
                                      parent=self.app)
        self.assertEqual(self.app.status.cget('text'),
                         runcom.tr('Sudo-lösenordet kunde inte verifieras.'))
        self.assertFalse(self.app._sudo_password_attempted)

    def test_wrong_sudo_password_reopens_dialog_then_reports_success(self):
        with patch.object(self.app.terminal, 'send'):
            self.app.prompt_sudo_password()
            self.app._sudo_password_entry.insert(0, 'wrong-secret')
            self.app._sudo_password_entry.event_generate('<Return>')
            self.app.update()
            self.app.prompt_sudo_password()  # sudo requested another attempt
            self.assertEqual(self.app._sudo_password_error.cget('text'),
                             runcom.tr('Fel lösenord. Försök igen.'))
            self.app._sudo_password_entry.insert(0, 'correct-secret')
            self.app._sudo_password_entry.event_generate('<Return>')
            self.app.update()
            self.app.sudo_password_accepted()
        self.assertEqual(self.app.status.cget('text'),
                         runcom.tr('Lösenordet är korrekt. Sudo är nu aktivt.'))
        self.assertFalse(self.app._sudo_password_attempted)

    @unittest.skipIf(os.name == 'nt', 'Unix sudo session')
    def test_startup_sudo_opens_graphical_dialog_and_accepts_password(self):
        fake_bin = Path(self.folder.name) / 'graphical-bin'
        fake_bin.mkdir()
        log = Path(self.folder.name) / 'graphical-sudo.log'
        fake = fake_bin / 'sudo'
        fake.write_text(
            '#!/bin/sh\n'
            'case "$1" in\n'
            '  -k) exit 0;;\n'
            '  -n) exit 1;;\n'
            '  -p)\n'
            '    printf "%s" "$2" >&2\n'
            '    stty -echo\n'
            '    IFS= read -r password\n'
            '    stty echo\n'
            '    printf "\\n" >&2\n'
            '    if [ "$password" = graphical-secret ]; then\n'
            '      printf "accepted\\n" >> ' + runcom.shlex.quote(str(log)) + '\n'
            '      exit 0\n'
            '    fi\n'
            '    exit 1;;\n'
            'esac\n')
        fake.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(fake_bin) + os.pathsep + os.environ.get('PATH', '')}):
            self.app.startup_sudo()
            self.pump_until(lambda: getattr(self.app, '_sudo_password_window', None) is not None)
            self.app._sudo_password_entry.insert(0, 'graphical-secret')
            self.app._sudo_password_entry.event_generate('<Return>')
            self.pump_until(lambda: log.exists() and 'accepted' in log.read_text())
            self.pump_until(lambda: self.app.terminal.sudo_state.get() == 'Sudo: aktivt under appsessionen')
            self.pump_until(lambda: self.app.status.cget('text') ==
                            runcom.tr('Lösenordet är korrekt. Sudo är nu aktivt.'))
        self.assertNotIn('graphical-secret', self.app.terminal.display.get('1.0', 'end'))

    @unittest.skipIf(os.name == 'nt', 'Unix sudo session')
    def test_sudo_script_uses_existing_terminal(self):
        script = Path(self.folder.name) / 'script with spaces.sh'
        script.write_text("printf '\\nsudo-script-ok\\n'\n")
        self.app.load_path(script)
        fake_bin = Path(self.folder.name) / 'bin'
        fake_bin.mkdir()
        fake = fake_bin / 'sudo'
        fake.write_text('#!/bin/sh\n'
                        'case "$1" in -k|-v|-n) exit 0;; esac\n'
                        '[ "$1" = "--" ] && shift\nexec "$@"\n')
        fake.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(fake_bin) + os.pathsep + os.environ.get('PATH', '')}):
            self.app.open_terminal()
            original = self.app.terminal.session
            self.app.run_with_sudo()
            self.pump_until(lambda: '\nsudo-script-ok\n' in self.app.terminal.display.get('1.0', 'end'))
            self.pump_until(lambda: self.app.terminal.sudo_state.get() == 'Sudo: aktivt under appsessionen')
            self.assertIs(self.app.terminal.session, original)
            self.assertTrue(self.app.bind('<F8>'))

    @unittest.skipIf(os.name == 'nt', 'Unix sudo routing')
    def test_script_with_sudo_runs_entire_script_elevated(self):
        script = Path(self.folder.name) / 'mixed-privileges.sh'
        script.write_text("printf '\\nouter:%s\\n' \"${RUNCOM_FAKE_SUDO:-user}\"\n"
                          "sudo sh -c 'printf \"inner:%s\\n\" \"${RUNCOM_FAKE_SUDO:-user}\"'\n")
        self.app.load_path(script)
        fake_bin = Path(self.folder.name) / 'bin'
        fake_bin.mkdir()
        fake = fake_bin / 'sudo'
        fake.write_text('#!/bin/sh\n'
                        'case "$1" in -k|-v|-n) exit 0;; esac\n'
                        '[ "$1" = "--" ] && shift\n'
                        'RUNCOM_FAKE_SUDO=root exec "$@"\n')
        fake.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(fake_bin) + os.pathsep + os.environ.get('PATH', '')}):
            self.app.run_in_app()
            panel = self.app.terminal
            self.pump_until(lambda: 'inner:root' in panel.display.get('1.0', 'end'))
        output = panel.display.get('1.0', 'end')
        self.assertIn('outer:root', output)
        self.assertIn('inner:root', output)

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

    def test_edit_button_is_the_only_file_list_action_that_opens_editor(self):
        path = Path(self.folder.name) / 'selected file.py'
        path.write_text('print("selected-run-ok")\n')
        self.app.refresh_list()
        self.app.listbox.selection_set(self.app.files.index(path))
        self.app.btn_edit_selected.invoke()
        self.assertEqual(self.app.current, path)
        self.assertIn('selected-run-ok', self.app.editor.get('1.0', 'end'))

    def test_double_click_action_runs_without_opening_file_in_editor(self):
        path = Path(self.folder.name) / 'selected file.py'
        path.write_text('print("selected-run-ok")\n')
        self.app.refresh_list()
        self.app.listbox.selection_set(self.app.files.index(path))
        self.app._on_list_run()
        self.pump_until(lambda: self.app.proc is None)
        self.assertIsNone(self.app.current)
        self.assertEqual(self.app.tabs.select(), self.app.tabs.tabs()[0])
        self.assertIn('selected-run-ok', self.app.output.get('1.0', 'end'))

    def test_open_and_run_file_picker(self):
        path = Path(self.folder.name) / 'picked.py'
        path.write_text('print("picked-run-ok")\n')
        with patch.object(runcom.filedialog, 'askopenfilename', return_value=str(path)):
            self.app.btn_open_run.invoke()
        self.pump_until(lambda: self.app.proc is None)
        self.assertIn('picked-run-ok', self.app.output.get('1.0', 'end'))

    def test_open_and_run_preserves_unsaved_editor_and_runs_other_file(self):
        path = Path(self.folder.name) / 'other.py'
        path.write_text('print("other-file-ran")\n')
        self.app.editor.insert('1.0', 'unsaved edits')
        self.app._open_and_run_path(path)
        self.pump_until(lambda: self.app.proc is None)
        self.assertIsNone(self.app.current)
        self.assertEqual(self.app.editor.get('1.0', 'end-1c'), 'unsaved edits')
        self.assertIn('other-file-ran', self.app.output.get('1.0', 'end'))

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
