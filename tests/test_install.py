import ctypes
import ctypes.util
import os
import sys
import time
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipIf(os.name == 'nt', 'Bash installer test')
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='runcom install ')
        self.root = Path(self.temp.name)
        self.fixture = self.root / 'release.zip'
        self.archive({'release/runcom.py': 'print("installed")\n', 'release/requirements.txt': '# No dependencies\n'})
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        curl = bin_dir / 'curl'
        curl.write_text('''#!/usr/bin/env python3
import json,os,pathlib,shutil,sys
if os.environ.get('RUNCOM_FAIL_DOWNLOAD') == '1': sys.exit(22)
with open(os.environ['RUNCOM_REQUESTS'],'a') as log: log.write(' '.join(sys.argv[1:])+'\\n')
out=sys.argv[sys.argv.index('-o')+1]
if 'releases/latest' in ' '.join(sys.argv):
    pathlib.Path(out).write_text(json.dumps({'zipball_url':'https://example.test/release.zip'}))
else:
    shutil.copyfile(os.environ['RUNCOM_FIXTURE'],out)
''')
        curl.chmod(0o755)
        self.install = self.root / 'app with spaces'
        self.env = dict(os.environ, PATH=str(bin_dir)+os.pathsep+os.environ['PATH'],
                        RUNCOM_FIXTURE=str(self.fixture), RUNCOM_INSTALL_DIR=str(self.install),
                        RUNCOM_REQUESTS=str(self.root/'requests.log'), XDG_DATA_HOME=str(self.root/'xdg data'), PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, files):
        with zipfile.ZipFile(self.fixture, 'w') as archive:
            for name, data in files.items(): archive.writestr(name, data)

    def run_installer(self, *args):
        return subprocess.run(['bash', str(ROOT/'install.sh'), *args], env=self.env, text=True, capture_output=True)

    def test_language_is_saved_changed_and_preserved_on_update(self):
        self.archive({'release/runcom.py': 'TRANSLATIONS = {}\n'})
        for args, expected in [(('--lang', 'en'), 'en'), ((), 'en'), (('--lang', 'sv'), 'sv')]:
            result = self.run_installer(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((self.install / 'runcom-language').read_text(), expected)

    def test_install_survives_temp_cleanup_and_can_update(self):
        for output in ('installed', 'updated'):
            self.archive({'release/runcom.py': 'print('+repr(output)+')\n'})
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual(subprocess.check_output([str(self.install/'runcom')], text=True).strip(), output)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux program menu')
    def test_menu_shortcut_launches_and_update_reuses_entry(self):
        library = ctypes.util.find_library('gio-2.0')
        if not library:
            self.skipTest('GIO unavailable for native desktop-entry validation')
        # Python 3.8's bundled ensurepip cannot bootstrap some exotic paths.
        # Still verify native menu launch there; stress quoting on newer runtimes.
        name = ('Runcom with spaces' if sys.version_info < (3, 9)
                else 'Runcom % with "quotes" $dollar `tick` and spaces')
        self.install = self.root / name
        self.env['RUNCOM_INSTALL_DIR'] = str(self.install)
        marker = self.root/'launched.txt'
        self.archive({'release/runcom.py': 'from pathlib import Path\nPath('+repr(str(marker))+').write_text("launched")\n',
                      'release/runcom.png': (ROOT/'runcom.png').read_bytes()})
        for _ in range(2):
            result = self.run_installer('--ref','main')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        applications = Path(self.env['XDG_DATA_HOME'])/'applications'
        entries = list(applications.glob('*.desktop'))
        self.assertEqual(len(entries),1)
        entry=entries[0]
        self.assertIn('Terminal=false',entry.read_text())
        expected_icon = str(self.install/'runcom.png').replace('\\', '\\\\')
        self.assertIn('Icon='+expected_icon+'\n', entry.read_text())
        gio = ctypes.CDLL(library)
        gio.g_desktop_app_info_new_from_filename.argtypes=[ctypes.c_char_p]
        gio.g_desktop_app_info_new_from_filename.restype=ctypes.c_void_p
        gio.g_app_info_launch.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
        gio.g_app_info_launch.restype=ctypes.c_int
        gio.g_object_unref.argtypes=[ctypes.c_void_p]
        info=gio.g_desktop_app_info_new_from_filename(os.fsencode(entry))
        self.assertTrue(info,'GIO rejected the menu entry')
        try:
            error=ctypes.c_void_p()
            self.assertTrue(gio.g_app_info_launch(info,None,None,ctypes.byref(error)), 'Menu entry could not launch')
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline:
                time.sleep(0.05)
            self.assertEqual(marker.read_text(),'launched')
        finally:
            gio.g_object_unref(info)

    def test_main_ref_bypasses_old_release(self):
        result = self.run_installer('--ref', 'main')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        requests = (self.root/'requests.log').read_text()
        self.assertIn('/zipball/main', requests)
        self.assertNotIn('releases/latest', requests)

    def test_bundled_uninstaller_keeps_scripts_and_removes_both_menu_entries(self):
        if sys.version_info >= (3, 9):
            self.install = self.root / 'Runcom % with "quotes" and spaces'
            self.env['RUNCOM_INSTALL_DIR'] = str(self.install)
        self.archive({'release/runcom.py': 'print("installed")',
                      'release/uninstall.sh': (ROOT/'uninstall.sh').read_bytes()})
        result = self.run_installer('--ref', 'main')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        launcher = self.install / ('Uninstall Runcom.command' if sys.platform == 'darwin' else 'runcom-uninstall')
        self.assertTrue(launcher.is_file())
        personal = self.install/'my-script.py'
        personal.write_text('print("keep")')
        env = dict(self.env)
        env.pop('RUNCOM_INSTALL_DIR')
        declined = subprocess.run([str(launcher)], input='n\n', text=True,capture_output=True,env=env)
        self.assertEqual(declined.returncode,0,declined.stderr)
        self.assertTrue((self.install/'runcom.py').exists())
        removed = subprocess.run([str(launcher)], input='y\n', text=True,capture_output=True,env=env)
        self.assertEqual(removed.returncode,0,removed.stdout+removed.stderr)
        self.assertFalse((self.install/'runcom.py').exists())
        self.assertFalse((self.install/'venv').exists())
        self.assertFalse(launcher.exists())
        self.assertEqual(personal.read_text(),'print("keep")')
        if sys.platform.startswith('linux'):
            apps=Path(env['XDG_DATA_HOME'])/'applications'
            self.assertFalse((apps/'runcom.desktop').exists())
            self.assertFalse((apps/'runcom-uninstall.desktop').exists())

    def test_help_assets_are_available_offline(self):
        self.archive({'release/runcom.py': 'print("installed")',
                      **{'release/'+name: (ROOT/name).read_bytes()
                         for name in ('help.html','help.css','style.css','runcom.png','runcom.ico')}})
        result = self.run_installer('--ref','main')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for name in ('help.html','help.css','style.css','runcom.png','runcom.ico'):
            self.assertEqual((self.install/name).read_bytes(),(ROOT/name).read_bytes())

    def test_ref_is_url_encoded(self):
        result = self.run_installer('--ref', 'feature/new changes')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('/zipball/feature%2Fnew%20changes', (self.root/'requests.log').read_text())

    def test_archive_traversal_is_rejected(self):
        self.archive({'../escape': 'bad', 'release/runcom.py':'print(1)'})
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unsafe archive', result.stderr)
        self.assertFalse(self.install.exists())

    def test_multiple_roots_are_rejected(self):
        self.archive({'one/runcom.py':'print(1)', 'two/runcom.py':'print(2)'})
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('one project directory', result.stderr)

    def test_invalid_application_does_not_replace_installed_app(self):
        self.install.mkdir()
        (self.install/'runcom.py').write_text('original')
        self.archive({'release/runcom.py':'def invalid('})
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.install/'runcom.py').read_text(), 'original')

    def test_download_failure_leaves_installed_app_untouched(self):
        self.install.mkdir()
        (self.install/'runcom.py').write_text('original')
        self.env['RUNCOM_FAIL_DOWNLOAD'] = '1'
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.install/'runcom.py').read_text(), 'original')

    def test_file_replacement_failure_rolls_back_application(self):
        self.install.mkdir()
        (self.install/'runcom.py').write_text('original')
        (self.install/'help.html').mkdir()
        self.archive({'release/runcom.py': 'print("new")',
                      'release/help.html': '<h1>New help</h1>'})
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.install/'runcom.py').read_text(), 'original')
        self.assertFalse((self.install/'runcom-revision').exists())
        self.assertTrue((self.install/'help.html').is_dir())

    def test_options_have_clear_errors(self):
        for args in [('--ref',), ('--unknown',)]:
            self.assertEqual(self.run_installer(*args).returncode, 2)
        self.assertEqual(self.run_installer('--help').returncode, 0)
