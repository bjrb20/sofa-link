import asyncio
import argparse
import re
import socket
from unittest import IsolatedAsyncioTestCase, TestCase

from aiortc import RTCConfiguration, RTCPeerConnection

from server import bind_udp_in, port_range


def free_range(size):
    """Find `size` consecutive free UDP ports on loopback."""
    for base in range(47000, 60000, 97):
        sockets = []
        try:
            for port in range(base, base+size):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.append(s)
                s.bind(('127.0.0.1', port))
            return range(base, base+size)
        except OSError:
            continue
        finally:
            for s in sockets:
                s.close()
    raise RuntimeError('No free UDP range')


class UdpRangeTests(IsolatedAsyncioTestCase):
    async def test_port_zero_binds_inside_the_range_until_it_is_full(self):
        ports = free_range(3)
        bind_udp_in(ports)
        loop = asyncio.get_running_loop()
        transports = []
        for _ in ports:
            transport, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, local_addr=('127.0.0.1', 0))
            transports.append(transport)
        self.addCleanup(lambda: [t.close() for t in transports])
        self.assertEqual([t.get_extra_info('sockname')[1] for t in transports], list(ports))
        with self.assertRaises(OSError):
            await loop.create_datagram_endpoint(asyncio.DatagramProtocol, local_addr=('127.0.0.1', 0))
        transports[1].close()
        await asyncio.sleep(0)  # the socket closes on the next loop pass
        transport, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, local_addr=('127.0.0.1', 0))
        transports.append(transport)
        self.assertEqual(transport.get_extra_info('sockname')[1], ports[1], 'a closed port is used again')

    async def test_webrtc_host_candidates_use_the_range(self):
        ports = free_range(40)
        bind_udp_in(ports)
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))  # no public STUN, as on the host
        self.addAsyncCleanup(pc.close)
        pc.addTransceiver('video', direction='sendonly')
        pc.addTransceiver('audio', direction='sendonly')
        await pc.setLocalDescription(await pc.createOffer())
        found = [int(port) for port in re.findall(r'a=candidate:\S+ \d+ udp \d+ \S+ (\d+) typ host', pc.localDescription.sdp)]
        self.assertTrue(found)
        self.assertTrue(all(port in ports for port in found), found)


class PortRangeArgumentTests(TestCase):
    def test_parses_and_rejects(self):
        self.assertEqual(port_range('40000-40199'), range(40000, 40200))
        for bad in ('40000', '40199-40000', '80-90', '60000-70000', 'a-b'):
            with self.assertRaises(argparse.ArgumentTypeError):
                port_range(bad)
