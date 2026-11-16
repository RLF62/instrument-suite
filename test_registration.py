import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import tool_registration as hook

class RegistrationTests(unittest.TestCase):
 def reply(self,value,tool='meter'):
  client=MagicMock();client.__enter__.return_value=client
  client.makefile.return_value.__enter__.return_value=io.BytesIO(value)
  with patch.object(hook.socket,'socket',return_value=client),patch('builtins.print'):
   result=hook.register_installed(tool)
  return result,client
 def test_each_installed_controller_is_confirmed(self):
  for tool in hook.TOOLS:
   result,client=self.reply((json.dumps({'ok':True,'result':{'registered':[tool]}})+'\n').encode(),tool)
   self.assertTrue(result)
   self.assertEqual(json.loads(client.sendall.call_args.args[0]),{'action':'register','tool':tool})
   client.settimeout.assert_called_once_with(3)
 def test_missing_manager_does_not_fail_install(self):
  with patch.object(hook.socket,'socket',side_effect=FileNotFoundError),patch('builtins.print'):
   self.assertFalse(hook.register_installed('scope'))
 def test_busy_manager_does_not_report_success(self):
  self.assertFalse(self.reply(b'{"ok":false,"error":"busy"}\n')[0])
 def test_missing_controller_does_not_report_success(self):
  self.assertFalse(self.reply(b'{"ok":true,"result":{"registered":["scope"]}}\n')[0])
 def test_malformed_responses_do_not_fail_install(self):
  for raw in (b'bad\n',b'[]\n',b'{}\n',b'{"ok":true,"result":null}\n',b'{"ok":true}\n',b'x'*65537,b'{}'):
   self.assertFalse(self.reply(raw)[0])
 def test_unknown_instrument_is_rejected(self):
  with self.assertRaises(ValueError):hook.register_installed('unknown')
 def test_standalone_navigation_without_manager(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(hook,'SUITE',Path(folder)):
   self.assertFalse(hook.install_navigation(object(),'scope'))
 def test_standalone_supply_is_registered_without_claiming_integrated_meter(self):
  import manager_engine as engine
  import subprocess
  with tempfile.TemporaryDirectory() as folder:
   home=Path(folder);(home/'hp6033a').mkdir()
   (home/'hp6033a/app.py').write_text('standalone supply; install_meter(app)')
   suite=home/'instrument-suite';(suite/'hp34401a').mkdir(parents=True)
   with patch.multiple(engine,HOME=home,SUITE=suite),patch.object(engine,'active',side_effect=lambda service,*a:service=='hp6033a'),patch.object(engine.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
    self.assertEqual(set(engine.scan()),{'supply'})

if __name__=='__main__':unittest.main()

