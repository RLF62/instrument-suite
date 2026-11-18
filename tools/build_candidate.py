"""Build private signed test artifacts from the reviewed central installer ZIPs."""
import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from maintenance.security import canonical,safe_member,REPOS,verify_manifest
from maintenance.linux import LinuxHost

def apply_suite_templates(suite, payload):
    """Use the same reviewed supply views as the existing suite installer."""
    source = Path(suite)/'integration/templates'
    destination = Path(payload)/'templates'
    names = ('index.html', 'classic_dual_preview.html')
    if any(not (source/name).is_file() or (source/name).is_symlink() for name in names):
        raise SystemExit('Reviewed suite supply templates are missing or symlinked')
    if source.is_symlink() or destination.is_symlink():
        raise SystemExit('Unexpected template directory symlink')
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        target = destination/name
        if target.is_symlink():
            raise SystemExit('Unexpected payload template symlink')
        shutil.copy2(source/name, target)


def apply_supply_wrapper(suite, payload):
    """Include the reviewed fresh-HTTP entry module, preserving live wrappers at activation."""
    source = Path(suite)/'integration/supply_standalone.py'
    target = Path(payload)/'supply_standalone.py'
    if not source.is_file() or source.is_symlink() or source.parent.is_symlink() or target.is_symlink():
        raise SystemExit('Reviewed supply entry wrapper is missing or symlinked')
    shutil.copy2(source, target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',type=Path,required=True);parser.add_argument('--locks',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--key',type=Path,required=True);parser.add_argument('--public-key',type=Path,required=True)
    parser.add_argument('--release',default='v0.1.0');parser.add_argument('--sequence',type=int,default=1)
    args=parser.parse_args();suite=args.suite.resolve();args.output.mkdir(mode=0o700)
    catalog=json.loads((suite/'approved/catalog.json').read_text());host=LinuxHost()
    now=dt.datetime.now(dt.timezone.utc)
    manifest={'schema':1,'engine_api':1,'sequence':args.sequence,'release':args.release,'issued':now.isoformat(),'expires':(now+dt.timedelta(days=14)).isoformat(),'components':{}}
    # Prior publication commit IDs identify the reviewed package sources. The
    # candidate engine's own changes are recorded in the local development commit.
    commits={'suite':subprocess.check_output(['git','-C',str(suite),'rev-parse','HEAD'],text=True).strip(),
             'meter':'41044eb725a22c2da7ee2dfd8a573365eebcff8a','supply':'2bc023a181feb84071f422a3336f4691e604ff5e','scope':'1a934f730ee6c54e1ed5191f79e043fe38195834',
             'generator':'f68871ddfab48cd06ac1772ef15bd97122934ce5'}
    with tempfile.TemporaryDirectory() as tmp:
        for name in REPOS:
            source=suite
            if name!='suite':
                package=suite/'approved/packages'/(name+'.zip')
                if hashlib.sha256(package.read_bytes()).hexdigest()!=catalog['tools'][name]['sha256']:raise SystemExit('Reviewed installer checksum mismatch')
                source=Path(tmp)/(name+'-source');source.mkdir()
                with zipfile.ZipFile(package) as z:
                    for item in z.infolist():
                        if item.is_dir() or item.filename.startswith('.'):continue
                        rel=safe_member(item.filename)
                        if (item.external_attr>>16)&0o170000==0o120000:raise SystemExit('Unexpected installer symlink')
                        target=source.joinpath(*rel.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(item))
            payload=Path(tmp)/name;payload.mkdir()
            for file in host.managed(name,source):
                dest=payload/file.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
            shutil.copy2(args.locks/(name+'.lock'),payload/'requirements.lock')
            if name=='supply':
                subprocess.run([sys.executable,str(suite/'patch_hp.py'),str(payload/'app.py')],check=True)
                path=payload/'app.py';text=path.read_text().replace('from hp34401a import install as install_meter\ninstall_meter(app)\n\n','');path.write_text(text)
                if 'install_meter(app)' in text or 'ResourceManager' in text:raise SystemExit('Shared-adapter transformation failed')
                apply_suite_templates(suite, payload)
                apply_supply_wrapper(suite, payload)
            host.validate_payload(name,payload)
            filename=name+'.tar.gz';archive=args.output/filename
            with archive.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as gz,tarfile.open(fileobj=gz,mode='w') as tar:
                for file in sorted(payload.rglob('*')):
                    if not file.is_file():continue
                    rel=file.relative_to(payload).as_posix();safe_member(rel);data=file.read_bytes();item=tarfile.TarInfo(rel);item.size=len(data);item.mode=0o644;tar.addfile(item,io.BytesIO(data))
            component_version=args.release if name=='suite' else 'v0.1.0'
            manifest['components'][name]={'version':component_version,'commit':commits[name],'size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                                         'url':f'https://github.com/RLF62/{REPOS[name]}/releases/download/{component_version}/{filename}','requires':{} if name=='suite' else {'suite':'v0.1.0'}}
    (args.output/'manifest.json').write_bytes(canonical(manifest))
    subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(args.key),'-rawin','-in',str(args.output/'manifest.json'),'-out',str(args.output/'manifest.json.sig')],check=True)
    verify_manifest((args.output/'manifest.json').read_bytes(),(args.output/'manifest.json.sig').read_bytes(),args.public_key)
    print('SIGNED_LOCAL_CANDIDATE_READY',args.output)

if __name__=='__main__':main()
