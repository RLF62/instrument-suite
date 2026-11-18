"""Single unprivileged install queue on a local Unix socket."""
import json
import os
from pathlib import Path
import socketserver
import sys
import threading
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import manager_engine as engine

SOCKET=Path('/run/fischer-suite-manager/install.sock')

class Manager:
    def __init__(self):
        self.lock=threading.Lock();self.current=None
        engine.STATE.mkdir(parents=True,exist_ok=True)
        self.latest=engine.STATE/'latest.json'

    def save(self,job):
        engine.atomic(self.latest,job);self.current=job

    def recover(self):
        if self.latest.exists():
            job=json.loads(self.latest.read_text());self.current=job
            if job['state'] in ('queued','running'):
                work=engine.STATE/job['id']
                try:
                    if job.get('operation')=='remove':
                        committing=(work/'removal.json').exists() and json.loads((work/'removal.json').read_text()).get('stage')=='committing'
                        engine.recover_remove(job['tool'],work)
                        job.update(state='succeeded' if committing else 'failed',message='Removal completed after recovery.' if committing else 'Interrupted removal rolled back; controller restored.')
                    else:
                        engine.rollback(job['tool'],work)
                        job.update(state='failed',message='Installation interrupted; new service rolled back. Existing controllers preserved.')
                except Exception as exc:job.update(state='failed',message='Interrupted installation needs recovery: '+str(exc))
                self.save(job)
        engine.register()

    def status(self):
        installed={}
        try:installed=json.loads(engine.REGISTRY.read_text())['instruments']
        except (OSError,ValueError,KeyError):pass
        catalog=engine.catalog();rows=[]
        for key,item in catalog['tools'].items():
            allowed,reason=engine.removal_policy(key) if key in installed else (False,'')
            rows.append({'id':key,**{k:item[k] for k in ('name','description')},'installed':key in installed,'removable':allowed,'removal_reason':reason,**installed.get(key,{})})
        if 'generator' in installed:
            allowed,reason=engine.removal_policy('generator')
            rows.append({'id':'generator','name':'HP 33120A Function Generator','description':'15 MHz function/arbitrary waveform generator controller',
                         'installed':True,'removable':allowed,'removal_reason':reason,**installed['generator']})
        job=dict(self.current) if self.current else None
        if job:
            log=engine.STATE/job['id']/'install.log'
            if log.exists():
                with log.open('rb') as stream:
                    stream.seek(max(0,log.stat().st_size-6500));job['log']=stream.read(6500).decode(errors='replace')
        return {'version':catalog['version'],'tools':rows,'job':job}

    def work(self,job):
        folder=engine.STATE/job['id']
        def notify(message):job.update(state='running',message=message);self.save(dict(job))
        try:
            if job.get('operation')=='remove':time.sleep(.4)  # Let the initiating dashboard return its job ID first.
            folder.mkdir(mode=0o755);(folder/'install.log').touch()
            if job.get('operation')=='remove':
                result=engine.remove(job['tool'],folder,job['keep_settings'],notify)
                job.update(state='succeeded',result=result,message='Controller removed. '+('Settings will be restored on reinstall.' if job['keep_settings'] else 'Reinstall will use default server settings; a private recovery archive is retained.'))
            else:
                engine.provision(job['tool'],folder,notify)
                job.update(state='succeeded',message='Installed and registered. Open the tool to configure its connection.')
        except Exception as exc:
            job.update(state='failed',message=('Removal stopped: ' if job.get('operation')=='remove' else 'Installation stopped: ')+str(exc)+'. See recovery details in the log.')
        finally:
            try:self.save(job)
            finally:self.lock.release()

    def watch(self):
        while True:
            time.sleep(15)
            if self.lock.acquire(blocking=False):
                try:engine.register()
                except Exception:pass
                finally:self.lock.release()

    def execute(self,data):
        if not isinstance(data,dict):raise ValueError('Expected a request object')
        if data=={'action':'status'}:return self.status()
        action=data.get('action');keys={'action','tool','keep_settings','confirm'} if action=='remove' else {'action','tool'}
        if set(data)!=keys or data.get('tool') not in engine.APP_DIRS or action not in ('install','register','remove'):
            raise ValueError('Choose one approved instrument')
        if action=='install' and data.get('tool')=='generator':
            raise ValueError('Reinstall the HP 33120A with its signed updater')
        if action=='remove' and (type(data['keep_settings']) is not bool or data['confirm'] is not True):raise ValueError('Explicit confirmation is required')
        if data['action']=='register':
            if not self.lock.acquire(blocking=False):raise RuntimeError('Installation is running; registration follows completion')
            try:return {'registered':list(engine.register())}
            finally:self.lock.release()
        if not self.lock.acquire(blocking=False):raise RuntimeError('Another instrument installation is running')
        job={'id':uuid.uuid4().hex,'tool':data['tool'],'operation':action,'state':'queued','message':'Removal queued' if action=='remove' else 'Installation queued','started':time.time()}
        if action=='remove':job['keep_settings']=data['keep_settings']
        self.save(job)
        threading.Thread(target=self.work,args=(job,),daemon=True).start()
        return {'job':job['id']}

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        try:
            data=self.rfile.readline(4097)
            if len(data)>4096 or not data.endswith(b'\n'):raise ValueError('Invalid request size')
            result={'ok':True,'result':self.server.manager.execute(json.loads(data))}
        except Exception as exc:result={'ok':False,'error':str(exc)[:500]}
        self.wfile.write(json.dumps(result).encode()+b'\n')

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True

def main():
    manager=Manager();manager.recover()
    threading.Thread(target=manager.watch,daemon=True).start()
    if SOCKET.exists():SOCKET.unlink()
    with Server(str(SOCKET),Handler) as server:
        os.chmod(SOCKET,0o660);server.manager=manager;server.serve_forever()

if __name__=='__main__':main()
