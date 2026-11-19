"""Optional shared-menu integration; never connects to instrument hardware."""
import json
import socket
import sys
from pathlib import Path
SOCKET='/run/fischer-suite-manager/install.sock'
SUITE=Path('/home/pi/instrument-suite')
TOOLS=('meter','supply','scope')

def register_installed(tool):
    if tool not in TOOLS:raise ValueError('Unknown instrument')
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(SOCKET)
            client.sendall(json.dumps({'action':'register','tool':tool}).encode()+b'\n')
            with client.makefile('rb') as stream:raw=stream.readline(65537)
            if len(raw)>65536 or not raw.endswith(b'\n'):raise ValueError('Invalid manager response')
            reply=json.loads(raw)
        if not isinstance(reply,dict) or not reply.get('ok'):
            raise RuntimeError(reply.get('error','Manager request failed') if isinstance(reply,dict) else 'Invalid manager response')
        result=reply.get('result')
        if not isinstance(result,dict) or tool not in result.get('registered',[]):
            raise RuntimeError('Controller is not yet visible to the shared manager')
    except (OSError,ValueError,RuntimeError,TypeError) as exc:
        print('Controller installed. Shared-menu registration pending:',exc)
        return False
    print('Registered with the shared instrument menu:',tool)
    return True

def install_navigation(app,current):
    if current not in TOOLS:raise ValueError('Unknown instrument')
    if not (SUITE/'suite_navigation.py').is_file():return False
    location=str(SUITE)
    if location not in sys.path:sys.path.insert(0,location)
    from suite_navigation import install
    install(app,current=current,default=(current,))
    return True

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool',choices=TOOLS)
    register_installed(parser.parse_args().tool)
