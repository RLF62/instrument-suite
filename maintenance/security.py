"""Authenticated releases; this module never executes downloaded controller code."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

REPOS = {'suite': 'instrument-suite', 'meter': 'hp34401a-web-controller',
         'supply': 'hp6033a-web-controller', 'scope': 'tektronix-ethernet-controller',
         'generator': 'hp33120a-web-controller'}
PUBLISH_REPO = 'instrument-suite'
VERSION = re.compile(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)')
MAX_DOWNLOAD = 128 * 1024 * 1024
PRIVATE = {'config.json', 'registry.json', 'tools.json', 'connection.json',
           'appearance.json', 'preferences.json', 'presets.json', '.env',
           'measurement-selection.json', '.control_htpasswd', '.control_auth_mode'}

class MaintenanceError(RuntimeError):
    pass

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
        fd = os.open(path.parent, os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(name): os.unlink(name)

def github_url(url, repo=None, artifact=False):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port or p.query or p.fragment:
        raise MaintenanceError('Only credential-free HTTPS release URLs are accepted')
    if p.hostname != 'github.com':
        raise MaintenanceError('Release URL must use github.com')
    parts = p.path.strip('/').split('/')
    allowed = {PUBLISH_REPO} if repo is None else ({repo} if isinstance(repo, str) else set(repo))
    if len(parts) != 6 or parts[0] != 'RLF62' or parts[1] not in allowed or parts[2:4] != ['releases', 'download']:
        raise MaintenanceError('Expected an immutable RLF62 repository release asset URL')
    if not VERSION.fullmatch(parts[4]) or not re.fullmatch(r'[A-Za-z0-9_.-]+', parts[5]):
        raise MaintenanceError('Invalid versioned release asset')
    return url

class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urllib.parse.urlsplit(newurl)
        if p.scheme != 'https' or p.username or p.password or p.hostname not in {
            'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
            raise MaintenanceError('Rejected release download redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def download(url, destination, expected=None, size=None, maximum=MAX_DOWNLOAD):
    """Incomplete downloads never become cached artifacts."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent)
    try:
        opener = urllib.request.build_opener(HTTPSRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        h = hashlib.sha256(); count = 0
        request = urllib.request.Request(url, headers={'User-Agent': 'Fischer-Instrument-Suite/1'})
        with opener.open(request, timeout=30) as response, os.fdopen(fd, 'wb') as stream:
            fd = None
            if urllib.parse.urlsplit(response.geturl()).scheme != 'https':
                raise MaintenanceError('Download was not HTTPS')
            while True:
                data = response.read(65536)
                if not data: break
                count += len(data)
                if count > maximum: raise MaintenanceError('Download exceeds its size limit')
                h.update(data); stream.write(data)
            stream.flush(); os.fsync(stream.fileno())
        if size is not None and count != size: raise MaintenanceError('Download length mismatch; retry with a working connection')
        if expected is not None and h.hexdigest() != expected: raise MaintenanceError('SHA-256 mismatch; file rejected')
        os.replace(temporary, destination)
        return destination
    finally:
        if fd is not None: os.close(fd)
        if os.path.exists(temporary): os.unlink(temporary)

def verify_manifest(raw, signature, public_key, minimum=0, now=None):
    key = Path(public_key)
    if not key.is_file() or key.is_symlink(): raise MaintenanceError('A pinned release public key is required')
    with tempfile.TemporaryDirectory() as temp:
        message, sig = Path(temp)/'manifest.json', Path(temp)/'manifest.sig'
        message.write_bytes(raw); sig.write_bytes(signature)
        result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(key),
                                 '-rawin', '-in', str(message), '-sigfile', str(sig)],
                                capture_output=True, timeout=15)
        if result.returncode: raise MaintenanceError('Release signature is invalid; nothing will be installed')
    def require(condition):
        if not condition: raise ValueError('Manifest policy check failed')
    try:
        m = json.loads(raw)
        require(raw == canonical(m))
        require(m['schema'] == 1 and type(m['sequence']) is int and m['sequence'] >= minimum)
        require(VERSION.fullmatch(m['release']) and m['engine_api'] == 1)
        current = now or dt.datetime.now(dt.timezone.utc)
        issued = dt.datetime.fromisoformat(m['issued'].replace('Z', '+00:00'))
        expires = dt.datetime.fromisoformat(m['expires'].replace('Z', '+00:00'))
        require(issued <= current < expires and expires - issued <= dt.timedelta(days=120))
        require(isinstance(m['components'], dict) and 'suite' in m['components'])
        require(set(m['components']) <= set(REPOS))
        for name, item in m['components'].items():
            require(VERSION.fullmatch(item['version']) and re.fullmatch('[a-f0-9]{40}', item['commit']))
            require(re.fullmatch('[a-f0-9]{64}', item['sha256']))
            require(type(item['size']) is int and 0 < item['size'] <= MAX_DOWNLOAD)
            # Old signed manifests still use the original controller repositories.
            # New releases keep every archive in the instrument-suite release.
            github_url(item['url'], (REPOS[name], PUBLISH_REPO), artifact=True)
            require(item['url'].split('/')[-2] == (m['release'] if '/instrument-suite/' in item['url'] else item['version']))
            for dep, version in item.get('requires', {}).items():
                require(dep in REPOS and VERSION.fullmatch(version))
    except (ValueError, TypeError, KeyError, AssertionError) as exc:
        raise MaintenanceError('Invalid, expired, incompatible or replayed release metadata') from exc
    return m

def safe_member(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or p.is_absolute() or '..' in p.parts or ':' in name or any(x.startswith('.') for x in p.parts):
        raise MaintenanceError('Unsafe release archive path')
    if p.name in PRIVATE or p.suffix.lower() in {'.key', '.pem', '.crt'} or any(x in {'venv', 'captures', 'setup-backups', 'security', '.git'} for x in p.parts):
        raise MaintenanceError('Release contains private/runtime material')
    return p

def extract(archive, destination):
    destination = Path(destination); destination.mkdir(mode=0o700)
    total = 0; seen = set()
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            p = safe_member(member.name)
            if member.name in seen or not (member.isfile() or member.isdir()):
                raise MaintenanceError('Archive contains duplicate or special entries')
            seen.add(member.name); total += member.size
            if total > 256*1024*1024 or len(seen)>10000: raise MaintenanceError('Expanded release is too large')
            target = destination.joinpath(*p.parts)
            if member.isdir(): target.mkdir(parents=True, exist_ok=True, mode=0o755)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                with target.open('xb') as stream: shutil_copy(tar.extractfile(member), stream)
                target.chmod(0o644)
    return destination

def shutil_copy(source, target):
    while True:
        chunk = source.read(65536)
        if not chunk: return
        target.write(chunk)
