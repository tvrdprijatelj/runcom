import os
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
                        RUNCOM_REQUESTS=str(self.root/'requests.log'), PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, files):
        with zipfile.ZipFile(self.fixture, 'w') as archive:
            for name, data in files.items(): archive.writestr(name, data)

    def run_installer(self, *args):
        return subprocess.run(['bash', str(ROOT/'install.sh'), *args], env=self.env, text=True, capture_output=True)

    def test_install_survives_temp_cleanup_and_can_update(self):
        for output in ('installed', 'updated'):
            self.archive({'release/runcom.py': 'print('+repr(output)+')\n'})
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual(subprocess.check_output([str(self.install/'runcom')], text=True).strip(), output)

    def test_main_ref_bypasses_old_release(self):
        result = self.run_installer('--ref', 'main')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        requests = (self.root/'requests.log').read_text()
        self.assertIn('/zipball/main', requests)
        self.assertNotIn('releases/latest', requests)

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

    def test_options_have_clear_errors(self):
        for args in [('--ref',), ('--unknown',)]:
            self.assertEqual(self.run_installer(*args).returncode, 2)
        self.assertEqual(self.run_installer('--help').returncode, 0)
