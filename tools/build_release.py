"""Build signed release files from clean reviewed Git checkouts; never install them."""
import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance.linux import LinuxHost
from maintenance.security import canonical, safe_member, REPOS, VERSION, verify_manifest, MaintenanceError
from tools.build_candidate import apply_suite_templates, apply_supply_wrapper

def git(source, *args):
    result = subprocess.run(['git', '-C', str(source), *args], capture_output=True, check=True)
    return result.stdout

def checkout(source, name):
    source = Path(source).resolve()
    if git(source, 'rev-parse', '--show-toplevel').decode().strip() != str(source):
        raise MaintenanceError(name+': use the repository root')
    remote = git(source, 'remote', 'get-url', 'origin').decode().strip()
    repo = 'RLF62/'+REPOS[name]
    if remote not in ('https://github.com/'+repo, 'https://github.com/'+repo+'.git',
                       'git@github.com:'+repo+'.git'):
        raise MaintenanceError(name+': unexpected source repository')
    if git(source, 'status', '--porcelain', '--untracked-files=all').strip():
        raise MaintenanceError(name+': source checkout must be clean, including untracked files')
    commit = git(source, 'rev-parse', 'HEAD').decode().strip()
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise MaintenanceError(name+': invalid source commit')
    tracked = set(git(source, 'ls-files', '-z').decode().split('\0'))-{''}
    # Also reject ignored files selected by the managed-file policy.
    files = {}
    for file in LinuxHost().managed(name, source):
        rel = file.relative_to(source).as_posix()
        safe_member(rel)
        if rel not in tracked or not file.resolve().is_relative_to(source):
            raise MaintenanceError(name+': managed file is not a tracked source input')
        data = file.read_bytes()
        if data != git(source, 'show', 'HEAD:'+rel):
            raise MaintenanceError(name+': managed file differs from committed bytes')
        files[rel] = hashlib.sha256(data).hexdigest()
    for rel in tracked:
        if (source/rel).is_symlink():
            raise MaintenanceError(name+': source symlinks require review')
    if not files:
        raise MaintenanceError(name+': no managed source files')
    return {'repository':repo, 'commit':commit, 'files':files}

def lock_bytes(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise MaintenanceError('Dependency lock must be a regular file')
    data = path.read_bytes()
    if len(data)>1024*1024:
        raise MaintenanceError('Dependency lock is too large')
    rows = [line.strip() for line in data.decode().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]
    pattern = r'[A-Za-z0-9][A-Za-z0-9_.-]*==[A-Za-z0-9][A-Za-z0-9_.+!-]*(?: --hash=sha256:[a-f0-9]{64})+'
    if not rows or any(not re.fullmatch(pattern, row) for row in rows):
        raise MaintenanceError('Use exact wheel versions and SHA-256 hashes; lock directives and URLs are forbidden')
    names = [re.sub(r'[-_.]+','-', row.split('==')[0]).lower() for row in rows]
    if len(names) != len(set(names)):
        raise MaintenanceError('Duplicate dependency in lock')
    return data

def archive_payload(payload, archive):
    with archive.open('xb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as gz, tarfile.open(fileobj=gz,mode='w') as tar:
        for file in sorted(payload.rglob('*')):
            if file.is_symlink():
                raise MaintenanceError('Payload contains a symlink')
            if not file.is_file(): continue
            rel=file.relative_to(payload).as_posix();safe_member(rel)
            data=file.read_bytes(); item=tarfile.TarInfo(rel)
            item.size=len(data);item.mode=0o644
            tar.addfile(item,io.BytesIO(data))

def build(sources, locks, versions, release, sequence, key, public_key, output):
    if set(sources)!=set(REPOS) or set(versions)!=set(REPOS):
        raise MaintenanceError('Provide source paths and versions for all five components')
    if not VERSION.fullmatch(release) or any(not isinstance(v,str) or not VERSION.fullmatch(v) for v in versions.values()):
        raise MaintenanceError('Release and component versions must use vMAJOR.MINOR.PATCH')
    if versions['suite']!=release or type(sequence) is not int or sequence<1:
        raise MaintenanceError('Suite version must equal the release; sequence must be positive')
    sources={n:Path(p).resolve() for n,p in sources.items()}
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise MaintenanceError('Output already exists; never overwrite release artifacts')
    for path in (Path(key).resolve(),Path(public_key).resolve(),output):
        if any(path.is_relative_to(root) for root in sources.values()):
            raise MaintenanceError('Keep signing keys and release output outside source repositories')
    inputs={n:checkout(path,n) for n,path in sources.items()}
    locked={n:lock_bytes(Path(locks)/(n+'.lock')) for n in REPOS}
    now=dt.datetime.now(dt.timezone.utc)
    manifest={'schema':1,'engine_api':1,'sequence':sequence,'release':release,
              'issued':now.isoformat(),'expires':(now+dt.timedelta(days=30)).isoformat(),
              'build_inputs':inputs,'components':{}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fischer-release-',dir=output.parent) as temporary:
        staging=Path(temporary); artifacts=staging/'artifacts';artifacts.mkdir(mode=0o700)
        host=LinuxHost()
        for name in REPOS:
            source=sources[name]
            payload=staging/name;payload.mkdir()
            for rel in inputs[name]['files']:
                dest=payload/rel;dest.parent.mkdir(parents=True,exist_ok=True)
                # Recheck bytes rather than accepting a changed working tree mid-build.
                data=(source/rel).read_bytes()
                if hashlib.sha256(data).hexdigest()!=inputs[name]['files'][rel]:
                    raise MaintenanceError('Source changed during release build')
                dest.write_bytes(data)
            (payload/'requirements.lock').write_bytes(locked[name])
            inputs[name]['dependency_lock_sha256']=hashlib.sha256(locked[name]).hexdigest()
            if name=='supply':
                # Run the reviewed transformation from the staged suite snapshot.
                patcher=staging/'suite'/'patch_hp.py'
                subprocess.run([sys.executable,str(patcher),str(payload/'app.py')],check=True,capture_output=True)
                app=payload/'app.py';text=app.read_text().replace('from hp34401a import install as install_meter\ninstall_meter(app)\n\n','')
                if 'install_meter(app)' in text or 'ResourceManager' in text:
                    raise MaintenanceError('Shared-adapter transformation failed')
                app.write_text(text)
                apply_suite_templates(staging/'suite',payload)
                apply_supply_wrapper(staging/'suite',payload)
                inputs[name]['suite_overlay_commit']=inputs['suite']['commit']
            host.validate_payload(name,payload)
            archive=artifacts/(name+'.tar.gz');archive_payload(payload,archive)
            manifest['components'][name]={'version':versions[name],'commit':inputs[name]['commit'],
                'size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                'url':'https://github.com/RLF62/'+REPOS[name]+'/releases/download/'+versions[name]+'/'+archive.name,
                'requires':{} if name=='suite' else {'suite':release}}
        # Reject source changes during transformation or archive creation as well.
        for name,path in sources.items():
            current=checkout(path,name)
            if current['commit']!=inputs[name]['commit'] or current['files']!=inputs[name]['files']:
                raise MaintenanceError('Source changed during release build')
        raw=canonical(manifest);(artifacts/'manifest.json').write_bytes(raw)
        subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(key),'-rawin','-in',str(artifacts/'manifest.json'),
                        '-out',str(artifacts/'manifest.json.sig')],check=True,capture_output=True)
        verify_manifest(raw,(artifacts/'manifest.json.sig').read_bytes(),public_key)
        if output.exists() or output.is_symlink():
            raise MaintenanceError('Output appeared during build; existing files preserved')
        artifacts.rename(output)
    return manifest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in REPOS:parser.add_argument('--'+name,type=Path,required=True)
    for name in ('locks','versions','key','public-key','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--release',required=True);parser.add_argument('--sequence',type=int,required=True)
    args=parser.parse_args()
    if os.geteuid()==0:parser.error('Build as an ordinary user, never as root')
    try:
        result=build({n:getattr(args,n) for n in REPOS},args.locks,json.loads(args.versions.read_text()),
                     args.release,args.sequence,args.key,args.public_key,args.output)
        print(json.dumps({'release':result['release'],'output':str(args.output),'installed':False}))
    except (MaintenanceError,OSError,ValueError,subprocess.SubprocessError):
        print('Release build rejected; inspect clean source checkouts, versions, dependency locks and signing keys. No installation performed.',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
