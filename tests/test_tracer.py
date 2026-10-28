import ctypes
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import tracer

ROOT = Path(__file__).resolve().parents[1]
# Does what the macOS core's retro_init does, then waits for Ctrl+C.
CHILD = f'''
import ctypes, os, signal, sys, time
sys.path.insert(0, {str(ROOT)!r})
import tracer
tracer.supervise()
assert ctypes.CDLL(None).ptrace(0, 0, None, 0) == 0  # PT_TRACE_ME
signal.signal(signal.SIGINT, lambda *_: sys.exit(3))
print(os.getpid(), flush=True)
while True:
    time.sleep(1)
'''


@unittest.skipUnless(platform.system() == 'Darwin', 'only the macOS core asks to be traced')
class TracerTests(unittest.TestCase):
    def start(self, env=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        script = Path(directory.name)/'child.py'
        script.write_text(CHILD)
        process = subprocess.Popen([sys.executable, script], stdout=subprocess.PIPE, env=env)
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.kill)
        return process, int(process.stdout.readline())

    def test_without_tracer_ctrl_c_stops_the_host(self):
        process, pid = self.start(dict(os.environ, **{tracer.CHILD: '1'}))
        os.kill(pid, signal.SIGINT)
        _, status = os.waitpid(pid, os.WUNTRACED)
        self.assertTrue(os.WIFSTOPPED(status))
        self.assertEqual(os.WSTOPSIG(status), signal.SIGINT)
        ctypes.CDLL(None).ptrace(8, pid, None, 0)  # PT_KILL; SIGKILL waits for the tracer
        process.wait(5)

    def test_ctrl_c_reaches_the_host_and_sigpipe_stays_ignored(self):
        process, pid = self.start()
        os.kill(pid, signal.SIGPIPE)
        time.sleep(.3)
        self.assertIsNone(process.poll())
        os.kill(pid, signal.SIGINT)
        self.assertEqual(process.wait(5), 3)

    def test_sigterm_to_the_supervisor_ends_the_host(self):
        process, _ = self.start()
        process.terminate()
        self.assertEqual(process.wait(5), 128+signal.SIGTERM)
