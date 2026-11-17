"""Enroll an administrator-pinned LOCAL test candidate on an empty test card."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from maintenance.security import verify_manifest,extract,atomic_json,MaintenanceError
import hashlib

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--key',type=Path,required=True)
    a=p.parse_args();root=Path('/var/lib/fischer-suite-updater');config=Path('/etc/fischer-suite-updater.json')
    if os.geteuid()!=0:raise SystemExit('Root enrollment required')
    if config.exists() or Path('/usr/local/bin/instrument-suite').exists():raise SystemExit('Existing updater preserved')
    for folder in ('hp6033a','hp34401a','instrument-suite','tektronix-controller'):
        if (Path('/home/pi')/folder).exists():raise SystemExit('Enrollment is for an empty test card; existing applications preserved')
    manifest=verify_manifest((a.directory/'manifest.json').read_bytes(),(a.directory/'manifest.json.sig').read_bytes(),a.key)
    archive=a.directory/'suite.tar.gz';item=manifest['components']['suite']
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=item['sha256'] or archive.stat().st_size!=item['size']:raise SystemExit('Candidate suite checksum mismatch')
    engine_root=Path('/opt/fischer-suite-updater');engine_root.mkdir(mode=0o755)
    engine=engine_root/'engine-v1';engine.mkdir(mode=0o755)
    with tempfile.TemporaryDirectory() as tmp:
        verified=extract(archive,Path(tmp)/'source');shutil.copytree(verified/'maintenance',engine/'maintenance')
    for directory,dirs,files in os.walk(engine):
        os.chmod(directory,0o755)
        for name in files:os.chmod(Path(directory)/name,0o644)
    key=engine_root/'candidate-release.pub';shutil.copy2(a.key,key);key.chmod(0o644)
    runner=engine/'runner.py';runner.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parent))\nfrom maintenance.cli import main\nraise SystemExit(main())\n');runner.chmod(0o644)
    (engine_root/'current').symlink_to(engine,target_is_directory=True)
    wrapper=Path('/usr/local/bin/instrument-suite');wrapper.write_text('#!/bin/sh\nexec /usr/bin/python3 -I /opt/fischer-suite-updater/current/runner.py "$@"\n');wrapper.chmod(0o755)
    root.mkdir(mode=0o755,exist_ok=True);root.chmod(0o755)
    atomic_json(config,{'schema':1,'key':str(key)})
    atomic_json(root/'candidate-mode.json',{'local_test_only':True,'public_release_published':False})
    print('LOCAL_CANDIDATE_ENROLLED_NO_CONTROLLERS_STARTED')

if __name__=='__main__':main()
