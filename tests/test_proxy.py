from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

from server import local_proxy, same_origin

TAILNET = 'host.example.ts.net:8443'
FORWARDED = {'Host': TAILNET, 'Origin': 'https://'+TAILNET,
             'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '100.64.0.7'}


async def echo(request):
    return web.json_response(dict(scheme=request.scheme, remote=request.remote))


class ProxyTests(IsolatedAsyncioTestCase):
    async def test_tailscale_serve_join_passes_origin_check(self):
        app = web.Application(middlewares=[local_proxy, same_origin])
        app.router.add_post('/api/join', echo)
        async with TestClient(TestServer(app)) as client:
            response = await client.post('/api/join', headers=FORWARDED)
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), dict(scheme='https', remote='100.64.0.7'))
            response = await client.post('/api/join', headers={'Host': TAILNET, 'Origin': 'https://'+TAILNET})
            self.assertEqual(response.status, 403, 'without the proxy header the scheme stays http')

    async def test_forwarded_headers_ignored_from_lan_peer(self):
        transport = Mock()
        transport.get_extra_info.side_effect = lambda key, default=None: ('192.168.1.20', 5000) if key == 'peername' else default
        request = make_mocked_request('POST', '/api/join', headers=FORWARDED, transport=transport)
        seen = await local_proxy(request, lambda r: _async(r))
        self.assertEqual((seen.scheme, seen.remote), ('http', '192.168.1.20'))


async def _async(value):
    return value
