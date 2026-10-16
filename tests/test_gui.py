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
