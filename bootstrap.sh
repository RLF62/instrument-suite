#!/bin/bash
# Release preparation replaces the public-key marker. Never put a private key here.
set -euo pipefail
umask 077
RELEASE_PUBLIC_KEY_B64='LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQTV6YSs1Vk5Nd0luVWYrYzFOZ0RxUGpkblA3NlY3S1ZDK1VqYzA3NGo0eWs9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo='
die() { printf 'Instrument Suite: %s\n' "$*" >&2; exit 1; }
RELEASE_CHANNEL_READY='yes'
[[ "$RELEASE_CHANNEL_READY" == 'yes' ]] || die 'This release channel is disabled. Nothing was changed.'
[[ $EUID -eq 0 ]] || die 'Run sudo bash bootstrap.sh'
case "$RELEASE_PUBLIC_KEY_B64" in @*) die 'This is an unpublished development bootstrap. A maintainer must pin the release public key and sign a release first. Nothing was changed.';; esac
for command in curl python3 openssl base64; do command -v "$command" >/dev/null || die "Install prerequisite $command from Raspberry Pi OS packages first"; done
[[ -r /proc/device-tree/model ]] && grep -q 'Raspberry Pi' /proc/device-tree/model || die 'Use a Raspberry Pi running Raspberry Pi OS'
id pi >/dev/null 2>&1 || die 'The reviewed installers require the pi account and /home/pi'
case "$(uname -m)" in aarch64|armv7l|armv6l) ;; *) die 'Unsupported CPU architecture';; esac
available=$(df -Pk /home/pi | awk 'NR==2 {print $4}')
[[ "$available" -ge 524288 ]] || die 'Free at least 512 MiB before staging a release; more may be required for backups'
[[ ! -e /etc/fischer-suite-updater.json ]] || die 'Updater already exists. Use sudo instrument-suite install or update; bootstrap will not overwrite it'
staging=$(mktemp -d /tmp/fischer-bootstrap.XXXXXXXX)
trap 'rm -rf -- "$staging"' EXIT
printf '%s' "$RELEASE_PUBLIC_KEY_B64" | base64 --decode > "$staging/release.pub"
curl_options=(--fail --silent --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 180 --retry 2)
curl "${curl_options[@]}" --max-filesize 1048576 https://api.github.com/repos/RLF62/instrument-suite/releases/latest -o "$staging/latest.json"
manifest_url=$(python3 - "$staging/latest.json" <<'PY'
import json,sys,re
d=json.load(open(sys.argv[1]))
if d.get('draft') or d.get('prerelease'):raise SystemExit('A stable approved release is required')
urls={a['name']:a['browser_download_url'] for a in d.get('assets',[])}
u=urls.get('manifest.json','')
if not re.fullmatch(r'https://github.com/RLF62/instrument-suite/releases/download/v\d+\.\d+\.\d+/manifest.json',u) or urls.get('manifest.json.sig')!=u+'.sig':raise SystemExit('No approved signed manifest; nothing was installed')
print(u)
PY
)
curl "${curl_options[@]}" --max-filesize 1048576 "$manifest_url" -o "$staging/manifest.json"
curl "${curl_options[@]}" --max-filesize 1024 "$manifest_url.sig" -o "$staging/manifest.json.sig"
openssl pkeyutl -verify -pubin -inkey "$staging/release.pub" -rawin -in "$staging/manifest.json" -sigfile "$staging/manifest.json.sig" >/dev/null || die 'Manifest signature failed; nothing was installed'
# Only authenticated metadata is parsed to select executable content.
python3 - "$staging" <<'PY'
import datetime as dt,json,pathlib,re,sys
p=pathlib.Path(sys.argv[1]);raw=(p/'manifest.json').read_bytes();d=json.loads(raw)
if raw!=(json.dumps(d,sort_keys=True,separators=(',',':'))+'\n').encode() or d.get('schema')!=1 or d.get('engine_api')!=1:raise SystemExit('Invalid signed manifest')
now=dt.datetime.now(dt.timezone.utc);issued=dt.datetime.fromisoformat(d['issued'].replace('Z','+00:00'));expires=dt.datetime.fromisoformat(d['expires'].replace('Z','+00:00'))
if not issued<=now<expires or expires-issued>dt.timedelta(days=120):raise SystemExit('Expired or future release; check the Pi clock')
a=d['components']['suite'];url=a['url']
if not re.fullmatch(r'https://github.com/RLF62/instrument-suite/releases/download/v\d+\.\d+\.\d+/[A-Za-z0-9_.-]+',url) or not re.fullmatch('[a-f0-9]{64}',a['sha256']) or type(a['size']) is not int or not 0<a['size']<=134217728:raise SystemExit('Invalid approved suite artifact')
(p/'artifact-url').write_text(url)
PY
artifact_url=$(cat "$staging/artifact-url")
curl "${curl_options[@]}" --max-filesize 134217728 "$artifact_url" -o "$staging/suite.tar.gz"
python3 - "$staging" <<'PY'
import hashlib,json,pathlib,tarfile,sys
p=pathlib.Path(sys.argv[1]);a=json.loads((p/'manifest.json').read_text())['components']['suite'];archive=p/'suite.tar.gz'
if archive.stat().st_size!=a['size'] or hashlib.sha256(archive.read_bytes()).hexdigest()!=a['sha256']:raise SystemExit('Suite checksum/length verification failed')
dest=p/'verified';dest.mkdir();seen=set();total=0
with tarfile.open(archive,'r:gz') as t:
 for m in t:
  rel=pathlib.PurePosixPath(m.name);total+=m.size
  if m.name in seen or rel.is_absolute() or '..' in rel.parts or '\\' in m.name or ':' in m.name or any(x.startswith('.') for x in rel.parts) or not(m.isfile() or m.isdir()) or total>268435456 or len(seen)>10000:raise SystemExit('Unsafe archive rejected')
  seen.add(m.name);target=dest.joinpath(*rel.parts)
  if m.isdir():target.mkdir(parents=True,exist_ok=True)
  else:
   target.parent.mkdir(parents=True,exist_ok=True)
   with target.open('xb') as f:
    source=t.extractfile(m)
    while True:
     data=source.read(65536)
     if not data:break
     f.write(data)
   target.chmod(0o644)
PY
# The following module is from the authenticated suite payload, not a branch.
cd "$staging/verified"
/usr/bin/python3 -I -c 'import sys;sys.path.insert(0,sys.argv.pop(1));from maintenance.bootstrap_setup import main;raise SystemExit(main())' "$staging/verified" --manifest-url "$manifest_url" --key "$staging/release.pub" "$@"
