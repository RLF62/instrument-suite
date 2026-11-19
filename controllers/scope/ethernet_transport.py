"""Bound initial DNS, RPC discovery and TCP connection without global socket changes."""
import ipaddress
import queue
import socket
import threading
import time
import vxi11
from vxi11 import rpc
from vxi11.vxi11 import CoreClient, DEVICE_CORE_PROG, DEVICE_CORE_VERS


def remaining(deadline):
    seconds=deadline-time.monotonic()
    if seconds<=0:
        raise TimeoutError('Scope Ethernet discovery timed out.')
    return seconds


def resolve_ipv4(host,deadline):
    try:
        return str(ipaddress.IPv4Address(host))
    except ValueError:
        pass
    result=queue.Queue(maxsize=1)
    def resolve():
        try:
            addresses=socket.getaddrinfo(host,None,socket.AF_INET,socket.SOCK_STREAM)
            result.put((True,addresses[0][4][0]))
        except Exception as error:
            result.put((False,error))
    # A stalled resolver has no instrument transport and cannot retain our scope lock.
    threading.Thread(target=resolve,daemon=True,name='scope-dns').start()
    try:
        ok,value=result.get(timeout=remaining(deadline))
    except queue.Empty as error:
        raise TimeoutError('Scope hostname lookup timed out.') from error
    if not ok:
        raise value
    return value


class BoundedConnect:
    def connect(self):
        sock=socket.create_connection((self.host,self.port),timeout=remaining(self.discovery_deadline))
        try:
            sock.settimeout(remaining(self.discovery_deadline))
        except Exception:
            sock.close()
            raise
        self.sock=sock


class BoundedMapper(BoundedConnect,rpc.TCPPortMapperClient):
    def __init__(self,host,deadline):
        self.discovery_deadline=deadline
        super().__init__(host)


class BoundedCore(BoundedConnect,CoreClient):
    def __init__(self,host,deadline):
        self.discovery_deadline=deadline
        mapper=BoundedMapper(host,deadline)
        try:
            port=mapper.get_port((DEVICE_CORE_PROG,DEVICE_CORE_VERS,rpc.IPPROTO_TCP,0))
        finally:
            mapper.close()
        if not port:
            raise rpc.RPCError('Scope VXI-11 program is not registered.')
        super().__init__(host,port=port)


class BoundedInstrument(vxi11.Instrument):
    def open(self):
        if self.link is None and self.client is None:
            deadline=time.monotonic()+self.timeout
            host=resolve_ipv4(self.host,deadline)
            self.client=BoundedCore(host,deadline)
        return super().open()
