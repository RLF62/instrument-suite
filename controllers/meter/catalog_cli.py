"""Reinstall an approved dashboard if the last web controller was removed."""
import argparse
import json
import socket
import time

def request(data):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(4);s.connect('/run/fischer-suite-manager/install.sock');s.sendall(json.dumps(data).encode()+b'\n')
        with s.makefile('rb') as stream:r=json.loads(stream.readline(65536))
    if not r.get('ok'):raise RuntimeError(r.get('error','Catalog request failed'))
    return r['result']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('install','status'));p.add_argument('tool',nargs='?',choices=('meter','supply','scope'));a=p.parse_args()
    if a.action=='status':print(json.dumps(request({'action':'status'}),indent=2));return
    if not a.tool:p.error('Choose an approved instrument')
    job=request({'action':'install','tool':a.tool})['job'];message=None
    for _ in range(900):
        result=request({'action':'status'});current=result.get('job')
        if current and current['id']==job:
            if current['message']!=message:message=current['message'];print(message,flush=True)
            if current['state']=='succeeded':return
            if current['state']=='failed':raise RuntimeError(current['message'])
        time.sleep(1)
    raise RuntimeError('Installation is still running; inspect status before retrying')

if __name__=='__main__':main()
