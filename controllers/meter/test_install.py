import subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import install

class InstallTests(unittest.TestCase):
 def test_startup_wait_retries_missing_socket_before_success(self):
  failure=subprocess.CalledProcessError(7,['curl'])
  with patch.object(install,'run',side_effect=[failure,None]) as run,patch.object(install.time,'sleep') as sleep:
   install.wait_for_web()
   self.assertEqual(run.call_count,2);sleep.assert_called_once_with(.25)
 def test_startup_wait_has_a_fixed_bound(self):
  with patch.object(install,'run',side_effect=subprocess.CalledProcessError(7,['curl'])) as run,patch.object(install.time,'sleep'):
   with self.assertRaises(subprocess.CalledProcessError):install.wait_for_web()
   self.assertEqual(run.call_count,20)
 def test_source_stage_is_distinct_from_installed_target(self):
  self.assertNotEqual(install.SOURCE,install.SUITE)
 def test_template_links_documentation(self):
  text=(install.SOURCE/'hp34401a/templates/meter.html').read_text()
  self.assertIn("docs/index.html",text)
 def test_new_configuration_blocks_hardware_and_writes(self):
  import json
  config=json.loads((install.SOURCE/'config.example.json').read_text())
  self.assertFalse(config['hardware_enabled']);self.assertTrue(config['meter_read_only'])
  self.assertFalse(config['supply_enabled'])
 def test_patch_rejects_unknown_source_without_modifying_it(self):
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'app.py';target.write_text('print(123)')
   result=subprocess.run([sys.executable,str(install.SOURCE/'patch_hp.py'),str(target)],capture_output=True)
   self.assertNotEqual(result.returncode,0);self.assertEqual(target.read_text(),'print(123)')
