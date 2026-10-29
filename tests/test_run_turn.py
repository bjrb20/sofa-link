import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT/'tools/run-turn.sh'
ADDRESSES = ['--lan-ip', '192.0.2.10', '--tailnet-host', 'host.example.ts.net']
PASSWORD = '0123456789abcdef0123456789abcdef'


class RunTurnConfigTests(unittest.TestCase):
    def setUp(self):
        # A copy of the script in a temporary repository, so that runtime/ is temporary too.
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root/'tools').mkdir()
        shutil.copy(SCRIPT, self.root/'tools/run-turn.sh')
        self.turn = self.root/'runtime/turn'

    def run_script(self, *args, path=None):
        env = dict(os.environ)
        if path:
            env['PATH'] = f'{path}:{env["PATH"]}'
        return subprocess.run(['bash', str(self.root/'tools/run-turn.sh'), '--config-only', *args],
                              capture_output=True, text=True, env=env)

    def keep_password(self):
        self.turn.mkdir(parents=True)
        (self.turn/'password').write_text(PASSWORD+'\n')

    def test_writes_ice_config_and_coturn_config(self):
        self.keep_password()
        result = self.run_script(*ADDRESSES)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'--ice-config {self.turn/"ice.json"}', result.stdout)
        ice = json.loads((self.turn/'ice.json').read_text())
        self.assertEqual(ice, [{'urls': ['turn:192.0.2.10:3478?transport=tcp',
                                         'turns:host.example.ts.net:5349?transport=tcp'],
                                'username': 'sofa', 'credential': PASSWORD}])
        conf = (self.turn/'turnserver.conf').read_text().splitlines()
        for line in ['listening-ip=192.0.2.10', 'listening-ip=127.0.0.1', 'listening-port=3478',
                     'relay-ip=127.0.0.1', 'realm=sofa-link', 'lt-cred-mech', f'user=sofa:{PASSWORD}',
                     'no-udp', 'no-tls', 'no-tcp-relay', 'no-multicast-peers', 'no-cli',
                     'allowed-peer-ip=192.0.2.10',
                     'denied-peer-ip=0.0.0.0-255.255.255.255',
                     'denied-peer-ip=::-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff']:
            self.assertIn(line, conf)
        self.assertFalse([line for line in conf if line.startswith(('no-auth', 'allow-loopback-peers'))])
        self.assertEqual([line for line in conf if line.startswith('allowed-peer-ip=')], ['allowed-peer-ip=192.0.2.10'],
                         'on macOS, a tailnet peer makes coturn close the allocation')
        quota = [int(line.split('=')[1]) for line in conf if line.startswith('total-quota=')]
        self.assertTrue(quota and 0 < quota[0] <= 32, quota)

    def test_files_are_private_and_under_runtime(self):
        result = self.run_script(*ADDRESSES)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(self.turn.stat().st_mode), 0o700)
        for name in ('password', 'ice.json', 'turnserver.conf'):
            self.assertEqual(stat.S_IMODE((self.turn/name).stat().st_mode), 0o600, name)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['runtime', 'tools'])
        ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', 'runtime/turn/ice.json'])
        self.assertEqual(ignored.returncode, 0, 'runtime/ must stay git-ignored')

    def test_makes_a_random_password_once_and_keeps_it(self):
        self.run_script(*ADDRESSES)
        password = (self.turn/'password').read_text().strip()
        self.assertRegex(password, r'^[0-9a-f]{48}$')
        self.run_script(*ADDRESSES)
        self.assertEqual((self.turn/'password').read_text().strip(), password)
        self.assertEqual(json.loads((self.turn/'ice.json').read_text())[0]['credential'], password)
        self.run_script(*ADDRESSES, '--new-password')
        self.assertNotEqual((self.turn/'password').read_text().strip(), password)

    def test_other_ports(self):
        self.keep_password()
        result = self.run_script(*ADDRESSES, '--port', '443', '--tls-port', '8443')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.turn/'ice.json').read_text())[0]['urls'],
                         ['turn:192.0.2.10:443?transport=tcp', 'turns:host.example.ts.net:8443?transport=tcp'])
        self.assertIn('listening-port=443', (self.turn/'turnserver.conf').read_text().splitlines())
        self.assertIn('tcp://127.0.0.1:443', result.stdout, 'the serve command uses the relay port')

    def test_tailnet_relay_on_a_plain_tcp_port(self):
        # Tailnet ACLs can allow only some ports, for example 22, 80 and 443.
        self.keep_password()
        result = self.run_script(*ADDRESSES, '--tailnet-tcp-port', '80')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.turn/'ice.json').read_text())[0]['urls'],
                         ['turn:192.0.2.10:3478?transport=tcp', 'turn:host.example.ts.net:80?transport=tcp'])
        self.assertIn('tailscale serve --bg --tcp 80 tcp://127.0.0.1:3478', result.stdout)
        self.assertNotIn('tls-terminated', result.stdout)

    def test_tailnet_only(self):
        # A LAN address that a player cannot reach makes the browser wait for it.
        self.keep_password()
        result = self.run_script(*ADDRESSES, '--tailnet-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.turn/'ice.json').read_text())[0]['urls'],
                         ['turns:host.example.ts.net:5349?transport=tcp'])
        conf = (self.turn/'turnserver.conf').read_text().splitlines()
        self.assertEqual([line for line in conf if line.startswith('allowed-peer-ip=')], ['allowed-peer-ip=192.0.2.10'])
        result = self.run_script('--lan-ip', '192.0.2.10', '--no-tailnet', '--tailnet-only')
        self.assertNotEqual(result.returncode, 0)

    def test_without_tailnet(self):
        self.keep_password()
        result = self.run_script('--lan-ip', '192.0.2.10', '--no-tailnet')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.turn/'ice.json').read_text())[0]['urls'],
                         ['turn:192.0.2.10:3478?transport=tcp'])
        conf = (self.turn/'turnserver.conf').read_text().splitlines()
        self.assertEqual([line for line in conf if line.startswith('allowed-peer-ip=')],
                         ['allowed-peer-ip=192.0.2.10'])

    def test_finds_the_tailnet_addresses(self):
        self.keep_password()
        bin_dir = self.root/'bin'
        bin_dir.mkdir()
        fake = bin_dir/'tailscale'
        fake.write_text('#!/bin/sh\n'
                        'case "$1" in\n'
                        '  ip) echo 100.64.0.20 ;;\n'
                        '  status) echo \'{"Self": {"DNSName": "found.example.ts.net."}, "Peer": {}}\' ;;\n'
                        'esac\n')
        fake.chmod(0o755)
        result = self.run_script('--lan-ip', '192.0.2.10', path=bin_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.turn/'ice.json').read_text())[0]['urls'],
                         ['turn:192.0.2.10:3478?transport=tcp', 'turns:found.example.ts.net:5349?transport=tcp'])
        conf = (self.turn/'turnserver.conf').read_text().splitlines()
        self.assertEqual([line for line in conf if line.startswith('allowed-peer-ip=')], ['allowed-peer-ip=192.0.2.10'])

    def fake_tools(self, system):
        bin_dir = self.root/'bin'
        bin_dir.mkdir(exist_ok=True)
        for name, body in (('uname', f'echo {system}'), ('id', 'case "$1" in -u) echo 1000 ;; -g) echo 1001 ;; esac'),
                           ('docker', f'printf "%s\\n" "$@" > {self.root}/docker-args')):
            (bin_dir/name).write_text(f'#!/bin/sh\n{body}\n')
            (bin_dir/name).chmod(0o755)
        return bin_dir

    def run_docker(self, system, *args):
        self.keep_password()
        env = dict(os.environ, PATH=f'{self.fake_tools(system)}:{os.environ["PATH"]}')
        result = subprocess.run(['bash', str(self.root/'tools/run-turn.sh'), '--docker', *args],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        docker = (self.root/'docker-args').read_text().splitlines()
        conf = (self.turn/'turnserver.conf').read_text().splitlines()
        self.assertEqual(docker[:2], ['run', '--rm'])
        self.assertIn(f'{self.turn}/turnserver.conf:/etc/coturn/turnserver.conf:ro', docker)
        self.assertIn('--user=1000:1001', docker, 'the container user can read the mode 600 file')
        self.assertEqual(docker[-3:], ['coturn/coturn:4.18.0', '-c', '/etc/coturn/turnserver.conf'])
        self.assertFalse([arg for arg in docker if PASSWORD in arg], 'no password on the command line')
        self.assertIn('pidfile=/tmp/turnserver.pid', conf)
        self.assertIn('userdb=/tmp/turndb', conf)
        self.assertIn('allowed-peer-ip=192.0.2.10', conf)
        self.assertIn('denied-peer-ip=0.0.0.0-255.255.255.255', conf)
        return docker, conf

    def test_docker_on_linux_uses_the_host_network(self):
        docker, conf = self.run_docker('Linux', *ADDRESSES)
        self.assertIn('--network=host', docker)
        self.assertFalse([arg for arg in docker if arg.startswith('--publish')])
        for line in ('listening-ip=192.0.2.10', 'listening-ip=127.0.0.1', 'relay-ip=127.0.0.1', 'listening-port=3478'):
            self.assertIn(line, conf)

    def test_docker_desktop_publishes_the_port(self):
        docker, conf = self.run_docker('Darwin', *ADDRESSES, '--port', '443')
        self.assertNotIn('--network=host', docker)
        self.assertIn('--publish=192.0.2.10:443:3478/tcp', docker)
        self.assertIn('--publish=127.0.0.1:443:3478/tcp', docker)
        # In the container, coturn listens and relays on its own address.
        self.assertFalse([line for line in conf if line.startswith(('listening-ip=', 'relay-ip='))])
        self.assertIn('listening-port=3478', conf)
        self.assertEqual([line for line in conf if line.startswith('allowed-peer-ip=')], ['allowed-peer-ip=192.0.2.10'])
        self.assertEqual(json.loads((self.turn/'ice.json').read_text())[0]['urls'][0],
                         'turn:192.0.2.10:443?transport=tcp')

    def test_rejects_bad_values(self):
        for args in (['--lan-ip', '192.0.2', '--no-tailnet'],
                     ['--lan-ip', '192.0.2.300', '--no-tailnet'],
                     ['--lan-ip', '192.0.2.10', '--tailnet-host', 'bad host\nno-auth'],
                     ['--lan-ip', '192.0.2.10', '--no-tailnet', '--port', '70000'],
                     ['--lan-ip', '192.0.2.10', '--no-tailnet', '--tailnet-tcp-port', '0'],
                     ['--unknown']):
            result = self.run_script(*args)
            self.assertNotEqual(result.returncode, 0, args)
            self.assertFalse((self.turn/'turnserver.conf').exists(), args)


if __name__ == '__main__':
    unittest.main()
