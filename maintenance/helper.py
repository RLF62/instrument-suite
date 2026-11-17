"""Restricted root queue: fixed actions; no shell, path, URL or password input."""
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import threading
import time
from . import cli
from .security import atomic_json
from .web_policy import read_policy

ALLOWED={'status','check','update','backup','rollback','firmware-status','firmware-prepare','firmware-flash','firmware-resume','firmware-cancel'}

def validate(request):
    if not isinstance(request,dict) or set(request)!={'schema','action'} or type(request['schema']) is not int or request['schema']!=1 or not isinstance(request['action'],str) or request['action'] not in ALLOWED:
        raise ValueError('Choose a fixed maintenance action; arguments are not accepted')
    return request['action']

class Queue:
    def __init__(self):
        self.lock=threading.Lock();self.job=None;self.path=cli.ROOT/'web-job.json'
        if self.path.exists():
            try:self.job=json.loads(self.path.read_text())
            except (OSError,ValueError):pass
            if self.job and self.job.get('state')=='running':self.job.update(state='interrupted',message='Helper restarted; inspect sudo instrument-suite status and rollback if recovery is pending')
    def execute(self,action):
        if action=='firmware-status':
            from .firmware import Firmware
            return {'firmware':Firmware().status(),'job':self.job}
        if action=='status':return {'software':cli.execute('status'),'job':self.job}
        if read_policy()['mode']=='disabled':raise PermissionError('Web updates are disabled by administrator policy')
        if not self.lock.acquire(blocking=False):raise RuntimeError('Another web maintenance operation is running')
        self.job={'action':action,'state':'running','started':time.time(),'message':'Preparing '+action}
        try:atomic_json(self.path,self.job)
        except BaseException:self.lock.release();raise
        def work():
            try:
                if action.startswith('firmware-'):
                    from .firmware import Firmware
                    result=Firmware().execute(action.removeprefix('firmware-'))
                else:result=cli.execute(action)
                self.job.update(state='succeeded',result=result,message='Maintenance action completed')
            except Exception as exc:self.job.update(state='failed',message=str(exc)[:1000])
            finally:
                try:atomic_json(self.path,self.job)
                finally:self.lock.release()
        threading.Thread(target=work,daemon=True).start()
        return {'queued':True,'action':action}

def bind_socket(path):
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    server.bind(str(path));os.chmod(path,0o660);server.listen(4)
    return server

def serve(path, permitted_uid):
    if os.geteuid()!=0:raise PermissionError('Root service required')
    path=Path(path)
    if path.exists():
        if path.is_symlink() or path.stat().st_uid!=0:raise PermissionError('Unexpected helper socket')
        path.unlink()
    server=bind_socket(path)
    queue=Queue()
    while True:
        connection,_=server.accept()
        with connection:
            connection.settimeout(4)
            try:
                credentials=connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i'))
                if struct.unpack('3i',credentials)[1] not in (0,permitted_uid):raise PermissionError('Unauthorized local caller')
                stream=connection.makefile('rb');raw=stream.readline(1025)
                if len(raw)>1024 or not raw.endswith(b'\n'):raise ValueError('Invalid request size')
                action=validate(json.loads(raw))
                result=queue.execute(action)
                reply={'ok':True,'result':result}
            except Exception as exc:reply={'ok':False,'error':str(exc)[:500]}
            connection.sendall(json.dumps(reply).encode()+b'\n')

def main():serve('/run/fischer-suite-updater-web/control.sock',pwd.getpwnam('pi').pw_uid)
if __name__=='__main__':main()
