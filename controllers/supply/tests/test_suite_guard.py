import importlib.util,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('suite_update_test',ROOT/'deploy/update.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class SuiteGuardTests(unittest.TestCase):
 def test_installer_can_be_sourced_and_main_refuses_integrated_app(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'app.py').write_text('# FISCHER_SHARED_ADAPTER_V1')
   result=subprocess.run(['bash','-c','source "$1"; APP_DIR="$2"; main','test',str(ROOT/'install.sh'),d],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0);self.assertIn('Shared instrument suite detected',result.stderr)
 def test_updater_rejects_suite_before_system_or_hardware_checks(self):
  import sys
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);app=home/'hp6033a';app.mkdir();(app/'app.py').write_text('# FISCHER_SHARED_ADAPTER_V1')
   with patch.object(Path,'home',return_value=home),patch.object(sys,'argv',['update','--release','v1.0.2','--url','http://localhost','--dry-run']),patch.object(u,'run') as run:
    with self.assertRaisesRegex(u.UpdateError,'Shared instrument suite detected'):u.main()
    run.assert_not_called()
