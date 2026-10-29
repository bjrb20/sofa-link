"""Start the relay with tools/run-turn.sh and check what it accepts.

Needs coturn: `turnserver` on PATH, or TURNSERVER=/path/to/turnserver.
Skipped without it.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest

from aioice.stun import TransactionFailed
from aioice.turn import create_turn_endpoint

ROOT = Path(__file__).resolve().parent.parent
TURNSERVER = os.environ.get('TURNSERVER') or shutil.which('turnserver')


def free_tcp_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Receiver(asyncio.DatagramProtocol):
    def __init__(self):
        self.received = asyncio.Queue()

    def datagram_received(self, data, addr):
        self.received.put_nowait((data, addr))


@unittest.skipUnless(TURNSERVER, 'coturn is not installed')
class TurnRelayTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        (cls.root/'tools').mkdir()
        shutil.copy(ROOT/'tools/run-turn.sh', cls.root/'tools/run-turn.sh')
        cls.port = free_tcp_port()
        cls.log = open(cls.root/'turnserver.log', 'w+')
        cls.relay = subprocess.Popen(['bash', str(cls.root/'tools/run-turn.sh'), '--no-tailnet', '--port', str(cls.port)],
                                     env=dict(os.environ, TURNSERVER=TURNSERVER), stdout=cls.log, stderr=subprocess.STDOUT)
        ice = cls.root/'runtime/turn/ice.json'
        for _ in range(100):
            try:
                if ice.exists():
                    cls.ice = json.loads(ice.read_text())[0]
                    cls.lan_ip = cls.ice['urls'][0].split(':')[1]
                    socket.create_connection((cls.lan_ip, cls.port), timeout=.2).close()
                    return
            except (OSError, ValueError):
                pass
            if cls.relay.poll() is not None:
                break
            subprocess.run(['sleep', '.1'])
        cls.tearDownClass()
        raise RuntimeError('The relay did not start')

    @classmethod
    def tearDownClass(cls):
        cls.relay.terminate()
        cls.relay.wait(10)
        cls.log.close()
        shutil.rmtree(cls.root)

    async def allocate(self, password):
        return await create_turn_endpoint(Receiver, (self.lan_ip, self.port), self.ice['username'], password,
                                          transport='tcp')

    async def test_wrong_password_is_refused(self):
        with self.assertRaises(TransactionFailed) as failure:
            await self.allocate('wrong-password')
        self.assertEqual(failure.exception.response.attributes['ERROR-CODE'][0], 401)

    async def test_relays_only_to_the_host(self):
        turn, client = await self.allocate(self.ice['credential'])
        inner = turn._TurnTransport__inner_protocol
        self.addAsyncCleanup(inner.delete)
        for peer in (('192.0.2.55', 9), ('8.8.8.8', 53), ('127.0.0.1', 9)):
            with self.assertRaises(TransactionFailed, msg=peer) as failure:
                await inner.channel_bind(0x4000, peer)
            self.assertEqual(failure.exception.response.attributes['ERROR-CODE'][0], 403, peer)

        loop = asyncio.get_running_loop()
        peer_transport, peer = await loop.create_datagram_endpoint(Receiver, local_addr=(self.lan_ip, 0))
        self.addCleanup(peer_transport.close)
        turn.sendto(b'to the host', peer_transport.get_extra_info('sockname'))
        data, relay_addr = await asyncio.wait_for(peer.received.get(), 5)
        self.assertEqual(data, b'to the host')
        peer_transport.sendto(b'to the browser', relay_addr)
        data, _ = await asyncio.wait_for(client.received.get(), 5)
        self.assertEqual(data, b'to the browser')


if __name__ == '__main__':
    unittest.main()
