import socket
import threading
import time
import unittest
from unittest.mock import patch
import scope_io
from ethernet_transport import resolve_ipv4


class DiscoveryTimeoutTests(unittest.TestCase):
    def test_stalled_mapper_times_out_and_releases_scope_lock(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
        port=listener.getsockname()[1];release=threading.Event()
        def stalled_peer():
            connection,_=listener.accept()
            try:
                connection.recv(4096);release.wait(2)
            finally:
                connection.close()
        peer=threading.Thread(target=stalled_peer,daemon=True);peer.start()
        try:
            with patch('ethernet_transport.rpc.PMAP_PORT',port):
                started=time.monotonic()
                with self.assertRaises(TimeoutError):
                    with scope_io.scope({'address':'127.0.0.1','timeout':.2}) as (scope,_):
                        scope.ask('*IDN?')
                self.assertLess(time.monotonic()-started,1)
            self.assertTrue(scope_io.THREAD_LOCK.acquire(blocking=False))
            scope_io.THREAD_LOCK.release()
            with scope_io.serialized():
                pass
        finally:
            release.set();peer.join(2);listener.close()

    def test_stalled_hostname_resolution_has_bounded_wait(self):
        release=threading.Event()
        def stalled_lookup(*args):
            release.wait(2)
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',0))]
        try:
            with patch('ethernet_transport.socket.getaddrinfo',stalled_lookup):
                started=time.monotonic()
                with self.assertRaises(TimeoutError):
                    resolve_ipv4('scope.invalid',time.monotonic()+.1)
                self.assertLess(time.monotonic()-started,.8)
        finally:
            release.set()


if __name__=='__main__':
    unittest.main()
