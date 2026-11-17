"""Operator-attended UsbGpib V2 application update. Never writes bootloader/fuses."""
from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess
import time
import urllib.request
import uuid
from .security import MaintenanceError, atomic_json
from .engine import exclusive
from .linux import LinuxHost

IMAGE = {
 'version':'V2.5',
 'commit':'ebe5042d42d57c29aefbbeb9a53ee0ad4ee3c6ad',
 'blob':'b96dfe1284bfdd96c4b0beaacd2f386adf64f86e',
 'size':14494,
 'sha256':'bd1e589663d006d08409eff03db6d75e2a02b12f1a288ff5a6b7847bfd26fb82',
}
IMAGE['url']='https://raw.githubusercontent.com/xyphro/UsbGpib/'+IMAGE['commit']+'/SW/binaries/TestAndMeasurement.bin'
MANUAL='https://github.com/xyphro/UsbGpib/blob/master/Tutorials/UsbGpibV2_manual.md#firmware-update-procedure'

def validate_image(data):
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if len(data)!=IMAGE['size'] or hashlib.sha256(data).hexdigest()!=IMAGE['sha256'] or blob!=IMAGE['blob']:
        raise MaintenanceError('Firmware identity mismatch; nothing was written')
    return data

def read(path):
    return Path(path).read_text().strip()

def devices(sys=Path('/sys/class/block')):
    found=[]
    for block in sys.iterdir():
        if (block/'partition').exists():continue
        target=block.resolve()
        usb=next((p for p in target.parents if (p/'idVendor').exists()),None)
        if usb is None or read(usb/'idVendor')!='03eb' or read(usb/'idProduct')!='2045':continue
        if read(block/'size')!='82' or read(block/'ro')!='0':
            raise MaintenanceError('Unexpected UsbGpib bootloader disk geometry; device preserved')
        if read(block/'device/vendor')!='LUFA' or read(block/'device/model')!='Bootloader':
            raise MaintenanceError('Unexpected bootloader SCSI identity; device preserved')
        node=Path('/dev')/block.name
        info=node.stat()
        if not stat.S_ISBLK(info.st_mode):raise MaintenanceError('Expected a real bootloader block device')
        found.append({'device':str(node),'sysfs':str(target),'usb':str(usb),'major_minor':read(block/'dev')})
    return found

def normal_usb(sys=Path('/sys/bus/usb/devices')):
    return [p.name for p in sys.iterdir() if (p/'idVendor').exists() and read(p/'idVendor')=='03eb' and read(p/'idProduct')=='2065']

class Firmware:
    def __init__(self, root=Path('/var/lib/fischer-suite-updater'), host=None):
        self.root=Path(root);self.directory=self.root/'firmware'
        self.pending=self.root/'firmware-pending.json'
        self.host=host or LinuxHost(self.root)
    def state(self):
        return json.loads(self.pending.read_text()) if self.pending.exists() else None
    def save(self,s):
        atomic_json(self.pending,s)
    def status(self):
        try:boot=devices();error=None
        except (OSError,MaintenanceError) as exc:boot=[];error=str(exc)
        return {'approved':IMAGE,'manual':MANUAL,'session':self.state(),
                'bootloaders':boot,'normal_adapters':normal_usb(),'device_error':error,
                'last_session':json.loads((self.directory/'last-session.json').read_text()) if (self.directory/'last-session.json').exists() else None}
    def execute(self,action):
        with exclusive(self.host.lock_path,allow_firmware=True):
            if (self.root/'pending.json').exists():raise MaintenanceError('Complete software recovery before adapter maintenance')
            if action=='prepare':return self.prepare()
            if action=='flash':return self.flash()
            if action=='resume':return self.resume()
            if action=='cancel':return self.cancel()
            raise MaintenanceError('Unknown firmware action')
    def prepare(self):
        if self.state():raise MaintenanceError('A firmware session is already pending; continue or cancel it')
        adapters=normal_usb()
        if devices() or len(adapters)!=1:raise MaintenanceError('Connect exactly one adapter in normal mode to a safe powered instrument before preparation')
        # Download first. No service is interrupted if verification fails.
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        request=urllib.request.Request(IMAGE['url'],headers={'User-Agent':'Fischer-Instrument-Suite'})
        with urllib.request.urlopen(request,timeout=30) as response:
            if response.geturl()!=IMAGE['url']:raise MaintenanceError('Unexpected firmware download redirect')
            data=validate_image(response.read(32769))
        image=self.directory/'FLASH.BIN'
        with image.open('wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        image.chmod(0o600)
        affected=[n for n in ('meter','supply') if self.host.active(n)]
        # Read-only guards verify OUTPUT OFF/remote disabled and paused acquisition.
        with self.host.quiesce(affected):
            if (self.root/'pending.flag').exists():raise MaintenanceError('Existing maintenance gate preserved')
            units=[self.host.service(n) for n in affected]
            if subprocess.run(['systemctl','is-active','--quiet','fischer-gpib'],capture_output=True).returncode==0:units.insert(0,'fischer-gpib')
            s={'id':uuid.uuid4().hex,'phase':'preparing','started':time.time(),'units':units,
               'image':IMAGE,'usb_port':adapters[0],'message':'Stopping shared GPIB access'}
            self.save(s)
            atomic_json(self.root/'pending.flag',{'components':['meter','supply'],'firmware':s['id']})
            (self.root/'pending.flag').chmod(0o644)
            for unit in reversed(units):self.host.run(['systemctl','stop',unit])
            s.update(phase='awaiting_bootloader',message='Disconnect ALL GPIB cables from the adapter. Keep USB connected and hold its button for about 3 seconds.')
            self.save(s)
        return s
    def selected(self):
        matches=devices()
        if len(matches)!=1:raise MaintenanceError('Connect exactly one UsbGpib bootloader; no disk was changed')
        if normal_usb():raise MaintenanceError('Disconnect other UsbGpib adapters before flashing')
        d=matches[0]
        # A mounted boot disk is never reused or unmounted on behalf of another app.
        mounts=json.loads(self.host.run(['findmnt','--json','--output','SOURCE,TARGET']))['filesystems']
        def flatten(items):
            for item in items:
                yield item
                yield from flatten(item.get('children',[]))
        if any(m.get('source','').split('[')[0]==d['device'] for m in flatten(mounts)):
            raise MaintenanceError('Bootloader is already mounted; unmount it before retrying')
        label=self.host.run(['blkid','-p','-s','LABEL','-o','value',d['device']]).strip()
        kind=self.host.run(['blkid','-p','-s','TYPE','-o','value',d['device']]).strip()
        if label!='GPIBUSBBOOT' or kind!='vfat':raise MaintenanceError('Bootloader filesystem identity mismatch')
        return d
    def revalidate(self,d):
        if self.selected()!=d:raise MaintenanceError('USB device changed; write refused')
    def mounted(self,d,mode,callback):
        mount=self.directory/'mount';mount.mkdir(exist_ok=True,mode=0o700)
        self.revalidate(d)
        self.host.run(['mount','-t','vfat','-o',mode+',nosuid,nodev,noexec',d['device'],mount])
        try:return callback(mount)
        finally:self.host.run(['umount',mount])
    def flash(self):
        s=self.state()
        if not s or s['phase'] not in ('awaiting_bootloader','write_failed','writing'):
            raise MaintenanceError('Prepare adapter maintenance before writing firmware')
        image=self.directory/'FLASH.BIN';data=validate_image(image.read_bytes())
        d=self.selected()
        if Path(d['usb']).name!=s.get('usb_port'):raise MaintenanceError('Reconnect the original adapter to its original USB port')
        backup=self.directory/('backup-'+uuid.uuid4().hex);backup.mkdir(mode=0o700)
        def inspect(mount):
            flash=mount/'FLASH.BIN';eeprom=mount/'EEPROM.BIN'
            if flash.is_symlink() or eeprom.is_symlink() or flash.stat().st_size!=24576 or eeprom.stat().st_size!=1023:
                raise MaintenanceError('Unexpected bootloader files; nothing written')
            original=flash.read_bytes();settings=eeprom.read_bytes()
            (backup/'FLASH.BIN').write_bytes(original);(backup/'EEPROM.BIN').write_bytes(settings)
            for p in backup.iterdir():
                p.chmod(0o600)
                with p.open('rb') as stream:os.fsync(stream.fileno())
            fd=os.open(backup,os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            return settings
        settings=self.mounted(d,'ro',inspect)
        if s.get('backup'):
            original_backup=Path(s['backup'])
            if not original_backup.resolve().is_relative_to(self.directory.resolve()):raise MaintenanceError('Invalid firmware backup location')
            if settings!=(original_backup/'EEPROM.BIN').read_bytes():raise MaintenanceError('EEPROM differs from the original backup; keep adapter in bootloader for attended recovery')
            backup=original_backup
        s.update(phase='writing',backup=str(backup),device=d,message='Writing application firmware; do not disconnect USB')
        self.save(s)
        try:
            def write_image(mount):
                if (mount/'FLASH.BIN').stat().st_size!=24576:raise MaintenanceError('FLASH.BIN changed before writing')
                self.host.run(['dd','if='+str(image),'of='+str(mount/'FLASH.BIN'),'bs=512','conv=notrunc','oflag=direct,sync'],timeout=90)
                self.host.run(['sync','-f',mount/'FLASH.BIN'])
            self.mounted(d,'rw',write_image)
            def verify(mount):
                actual=(mount/'FLASH.BIN').read_bytes()
                original=(backup/'FLASH.BIN').read_bytes()
                if len(actual)!=24576 or actual[:len(data)]!=data or actual[len(data):]!=original[len(data):]:raise MaintenanceError('Firmware readback mismatch; retry in bootloader')
                if (mount/'EEPROM.BIN').read_bytes()!=settings:raise MaintenanceError('EEPROM changed; keep adapter in bootloader for attended recovery')
            self.mounted(d,'ro',verify)
            s.update(phase='awaiting_power_cycle',write_verified=True,eeprom_unchanged=True,message='Write/readback verified. Unplug BOTH USB and GPIB. Connect GPIB to a safe powered instrument BEFORE USB to help drain residual adapter power and exit bootloader, then reconnect USB and verify/resume.')
            self.save(s);return s
        except Exception as exc:
            s.update(phase='write_failed',message=str(exc));self.save(s);raise
    def restore(self,s):
        gate=self.root/'pending.flag'
        if json.loads(gate.read_text()).get('firmware')!=s['id']:raise MaintenanceError('Maintenance gate ownership changed')
        for unit in s['units']:self.host.run(['systemctl','start',unit])
        # Require maintenance guard health, including while gated.
        affected=[n for n in ('meter','supply') if self.host.service(n) in s['units']]
        self.host.health(affected,[])
        gate=self.root/'pending.flag'
        if json.loads(gate.read_text()).get('firmware')!=s['id']:raise MaintenanceError('Maintenance gate ownership changed')
        gate.unlink()
        self.pending.unlink()
        atomic_json(self.directory/'last-session.json',s)
    def runtime_version(self,s):
        if devices() or normal_usb()!=[s.get('usb_port')]:raise MaintenanceError('Power-cycle the original adapter, reconnect it to the same USB port and a safe powered instrument')
        script="import sys; from pathlib import Path; sys.path.insert(0,'/home/pi/instrument-suite'); from adapter_worker import hardware; serial=(Path('/sys/bus/usb/devices')/"+repr(s['usb_port'])+"/'serial').read_text().strip(); resource='USB0::1003::8293::'+serial+'::0::INSTR'; print(hardware({'config':{'resource':resource},'request':{'target':'adapter','action':'inspect'}})['firmware'])"
        return self.host.run(['systemd-run','--quiet','--wait','--pipe','--collect','--uid=pi','--gid=www-data','--property=RuntimeMaxSec=20','--property=NoNewPrivileges=true','--property=PrivateTmp=true','--property=ProtectSystem=true','--property=RestrictSUIDSGID=true','--setenv=HOME=/home/pi','--setenv=PYTHONNOUSERSITE=1','/home/pi/instrument-suite/venv/bin/python','-c',script],timeout=30).strip()
    def resume(self):
        s=self.state()
        if not s or s['phase']!='awaiting_power_cycle':raise MaintenanceError('A verified write and physical power cycle are required')
        version=self.runtime_version(s)
        if version!=IMAGE['version']:raise MaintenanceError('Running firmware did not report '+IMAGE['version']+'; controllers remain paused')
        s.update(runtime_version=version,message='Application write, EEPROM preservation and running firmware verified')
        self.save(s);self.restore(s);s['phase']='completed';atomic_json(self.directory/'last-session.json',s);return s
    def cancel(self):
        s=self.state()
        if not s:return {'message':'No pending firmware session'}
        if s['phase'] not in ('preparing','awaiting_bootloader'):raise MaintenanceError('A write was attempted. Finish verification or retry flashing; cancellation cannot restore an unknown adapter')
        version=self.runtime_version(s)
        if not version.startswith('V'):raise MaintenanceError('Original adapter runtime could not be verified')
        s['runtime_version']=version
        s.update(phase='cancelled',message='Maintenance cancelled before any firmware write')
        self.save(s);self.restore(s);return s
