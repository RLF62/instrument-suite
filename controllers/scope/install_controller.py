"""Install the standalone Ethernet controller while retaining runtime preferences."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import time

SOURCE=Path(__file__).resolve().parent
HOME=Path.home()
TARGET=HOME/'tektronix-controller'
VENV=HOME/'tektronix-controller-venv'
UNIT=HOME/'.config/systemd/user/tektronix-controller.service'
NAMES=('app.py','archive_tools.py','ethernet_transport.py','example_catalog.py','scope_io.py',
       'screen_effect.py','tool_registration.py','index.html','setup.html','requirements.txt','README.md','DEPLOYMENT.md')

def run(*args,**kw):return subprocess.run(list(map(str,args)),check=True,timeout=180,**kw)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 g=p.add_mutually_exclusive_group(required=True);g.add_argument('--check',action='store_true');g.add_argument('--apply',action='store_true')
 args=p.parse_args()
 if os.getuid()==0:p.error('Run as the controller user, not root')
 if SOURCE==TARGET or TARGET in SOURCE.parents:p.error('Use a separate extracted staging directory')
 for name in NAMES:
  if not (SOURCE/name).is_file():p.error('Missing source: '+name)
 python=VENV/'bin/python'
 if not python.exists():
  if args.check:p.error('Create an isolated Python environment with requirements.txt first; then rerun --check')
  run('python3','-m','venv',VENV)
  run(python,'-m','pip','install','-r',SOURCE/'requirements.txt')
 run(python,'-m','unittest','discover','-p','test_*.py',cwd=SOURCE)
 if shutil.which('node'):
  for test in sorted(SOURCE.glob('test_*.js')):run('node',test,cwd=SOURCE)
 else:print('Node frontend checks skipped: install nodejs to run them.')
 if args.check:
  print('Checks passed. No services or hardware changed.');return
 # Dependencies are prepared before the service interruption.
 run(python,'-m','pip','install','-r',SOURCE/'requirements.txt')
 backup=HOME/'.tektronix-install-backups'/time.strftime('%Y%m%d-%H%M%S')
 backup.mkdir(parents=True,mode=0o700)
 managed=[TARGET/name for name in NAMES]+[TARGET/'docs',TARGET/'static',UNIT]
 existed={str(x):x.exists() for x in managed}
 for i,path in enumerate(managed):
  if path.is_dir():shutil.copytree(path,backup/str(i))
  elif path.exists():shutil.copy2(path,backup/str(i))
 was_active=subprocess.run(['systemctl','--user','is-active','--quiet','tektronix-controller']).returncode==0
 (backup/'ROLLBACK.txt').write_text('Stop the user service. Restore numbered files using manifest.txt; restore the old unit before daemon-reload/start. Runtime preferences were not copied over. The Python environment may have updated dependencies.\n')
 (backup/'manifest.txt').write_text('\n'.join(f'{i}: {path} existed={existed[str(path)]}' for i,path in enumerate(managed)))
 try:
  subprocess.run(['systemctl','--user','stop','tektronix-controller'],check=False,timeout=20)
  TARGET.mkdir(exist_ok=True)
  for name in NAMES:shutil.copy2(SOURCE/name,TARGET/name)
  shutil.copytree(SOURCE/'docs',TARGET/'docs',dirs_exist_ok=True)
  shutil.copytree(SOURCE/'static',TARGET/'static',dirs_exist_ok=True)
  UNIT.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(SOURCE/'tektronix-controller.service',UNIT)
  run('systemctl','--user','daemon-reload')
  run('systemctl','--user','enable','--now','tektronix-controller')
  run('sudo','loginctl','enable-linger',os.getlogin() if os.environ.get('USER') is None else os.environ['USER'])
  run('curl','-fsS','--max-time','10','--retry','5','--retry-connrefused','http://127.0.0.1:8081/',stdout=subprocess.DEVNULL)
 except Exception:
  subprocess.run(['systemctl','--user','stop','tektronix-controller'],timeout=20)
  for i,path in enumerate(managed):
   saved=backup/str(i)
   if saved.is_dir():shutil.copytree(saved,path,dirs_exist_ok=True)
   elif saved.exists():shutil.copy2(saved,path)
   elif path.is_file():path.unlink()
  run('systemctl','--user','daemon-reload')
  if was_active:run('systemctl','--user','start','tektronix-controller')
  raise
 from tool_registration import register_installed
 register_installed('scope')
 print(f'Installed. Backup: {backup}. Open port 8081, then Setup; no scope commands were sent by installation.')

if __name__=='__main__':main()
