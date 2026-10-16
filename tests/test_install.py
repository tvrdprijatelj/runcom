import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipIf(os.name == 'nt', 'Bash installer test')
class InstallerTests(unittest.TestCase):
    def test_install_survives_temp_cleanup_and_can_update(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = root / 'release.zip'
            with zipfile.ZipFile(fixture, 'w') as archive:
                archive.writestr('release/runcom.py', 'print("installed")\n')
                archive.writestr('release/requirements.txt', '# No dependencies\n')
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            curl = bin_dir / 'curl'
            curl.write_text('#!/usr/bin/env python3\nimport json,os,pathlib,shutil,sys\nout=sys.argv[sys.argv.index("-o")+1]\nif "releases/latest" in " ".join(sys.argv): pathlib.Path(out).write_text(json.dumps({"zipball_url":"https://example.test/release.zip"}))\nelse: shutil.copyfile(os.environ["RUNCOM_FIXTURE"],out)\n')
            curl.chmod(0o755)
            install = root / 'app with spaces'
            env = dict(os.environ, PATH=str(bin_dir)+os.pathsep+os.environ['PATH'], RUNCOM_FIXTURE=str(fixture), RUNCOM_INSTALL_DIR=str(install), PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
            for _ in range(2):
                result = subprocess.run(['bash', str(ROOT / 'install.sh')], env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertEqual(subprocess.check_output([str(install / 'runcom')], text=True).strip(), 'installed')
