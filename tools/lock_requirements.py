"""Resolve wheel-only dependencies on the target Pi, then hash-lock all wheels."""
import argparse
import email
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('requirements',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    if a.output.exists():raise SystemExit('Use a new output path and review lock changes')
    with tempfile.TemporaryDirectory(prefix='fischer-lock-') as tmp:
        subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--dest',tmp,'-r',str(a.requirements)],check=True)
        rows={}
        for wheel in Path(tmp).glob('*.whl'):
            with zipfile.ZipFile(wheel) as archive:
                names=[n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
                if len(names)!=1:raise SystemExit('Invalid wheel metadata')
                data=email.message_from_bytes(archive.read(names[0]))
            name,version=data['Name'],data['Version']
            if not name or not version or name in rows:raise SystemExit('Ambiguous wheel metadata')
            rows[name]=f'{name}=={version} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}'
        if not rows:raise SystemExit('No dependency wheels were resolved')
        a.output.write_text('# Reviewed hashes for the target Raspberry Pi OS/Python architecture.\n'+'\n'.join(rows[n] for n in sorted(rows,key=str.lower))+'\n')

if __name__=='__main__':main()
