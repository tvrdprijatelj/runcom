"""Real pseudo-terminal integration without elevated privileges."""
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runcom


@unittest.skipIf(os.name == 'nt', 'Unix PTY integration')
class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='runcom terminal ')
        self.session = runcom.TerminalSession(Path(self.folder.name), os.environ.copy())
        self.output = ''
        self.until('$ ')

    def tearDown(self):
        self.session.close()
        self.folder.cleanup()

    def until(self, marker, timeout=6):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                kind, value = self.session.events.get(timeout=0.1)
                if kind == 'text':
                    self.output += value
                if marker in self.output:
                    return
            except runcom.queue.Empty:
                pass
        self.fail('Terminal output did not contain ' + repr(marker) + ': ' + repr(self.output))

    def test_persistent_shell_directory_unicode_and_input(self):
        self.session.send("mkdir 'sub folder'; cd 'sub folder'; RUNCOM_TEST=kept\n")
        self.session.send("printf '\\n%s|%s|åäö\\n' \"$RUNCOM_TEST\" \"$PWD\"\n")
        self.until('kept|' + self.folder.name + '/sub folder|åäö')
        self.session.send("read -r reply; printf '\\nreply=%s\\n' \"$reply\"\n")
        self.session.send('hello world\n')
        self.until('reply=hello world')

    def test_password_input_is_not_echoed(self):
        program = Path(self.folder.name) / 'password.py'
        program.write_text('import getpass\ngetpass.getpass("Password: ")\nprint("accepted")\n')
        self.session.send(shlex.join([sys.executable, str(program)]) + '\n')
        self.until('Password: ')
        self.output = ''
        self.session.send('unique-test-password-7821\n')
        self.until('accepted')
        self.assertNotIn('unique-test-password-7821', self.output)

    def test_ctrl_c_returns_to_shell(self):
        self.session.send('sleep 60\n')
        deadline = time.monotonic() + 3
        while self.session.idle() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.session.idle())
        self.session.send('\x03')
        self.session.send("printf '\\ninterrupt-ok\\n'\n")
        self.until('\r\ninterrupt-ok\r\n')

    def test_close_immediately_after_start(self):
        second = runcom.TerminalSession(Path(self.folder.name), os.environ.copy())
        second.close()
        second.thread.join(timeout=2)
        self.assertIsNotNone(second.proc.poll())
        self.assertFalse(second.thread.is_alive())

    def test_close_reaps_shell(self):
        self.session.close()
        self.session.thread.join(timeout=2)
        self.assertIsNotNone(self.session.proc.poll())
        self.assertFalse(self.session.thread.is_alive())
        self.session.close()
