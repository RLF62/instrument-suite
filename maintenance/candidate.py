"""Explicit local signed-candidate testing. No public release is published here."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from .engine import Engine
from .linux import LinuxHost
from .security import MaintenanceError,verify_manifest,atomic_json

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path);p.add_argument('--key',type=Path,required=True)
    p.add_argument('--instruments',default='meter,supply,scope,generator');p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(argv)
    if os.geteuid()!=0:raise MaintenanceError('Signed-candidate testing requires the local administrator')
    directory=a.directory.resolve()
    if directory.stat().st_uid!=0 or directory.stat().st_mode&0o022:raise MaintenanceError('Candidate artifacts must be root-owned and protected')
    if a.key.stat().st_uid!=0 or a.key.stat().st_mode&0o022:raise MaintenanceError('Candidate public key must be administrator-pinned')
    root=Path('/var/lib/fischer-suite-updater');host=LinuxHost(root)
    def local_fetch(url,destination,expected=None,size=None,**kwargs):
        # Map an authenticated immutable asset URL to its prepositioned local copy.
        name=url.rsplit('/',1)[-1];source=directory/name
        if source.is_symlink() or not source.resolve().is_relative_to(directory) or not source.is_file():raise MaintenanceError('Missing candidate artifact')
        data=source.read_bytes()
        if expected is not None and hashlib.sha256(data).hexdigest()!=expected:raise MaintenanceError('Candidate checksum mismatch')
        if size is not None and len(data)!=size:raise MaintenanceError('Candidate length mismatch')
        shutil.copy2(source,destination);return Path(destination)
    engine=Engine(root,host,fetch=local_fetch)
    manifest=verify_manifest((directory/'manifest.json').read_bytes(),(directory/'manifest.json.sig').read_bytes(),a.key,minimum=engine.state()['sequence'])
    from .cli import selection
    result=engine.apply(manifest,selection(a.instruments),a.dry_run)
    print(json.dumps(result,indent=2))
    print('LOCAL CANDIDATE ONLY: public GitHub update discovery is not enabled by this test.')
    return 0

if __name__=='__main__':raise SystemExit(main())
