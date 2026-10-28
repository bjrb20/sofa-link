import asyncio
import ctypes
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import numpy as np

from emulator import Emulator
from inputs import InputHub
from media import Clock, GameAudio, GameVideo


class ClockTests(IsolatedAsyncioTestCase):
    async def test_stall_drops_missed_capture_slots(self):
        now = [10.]
        waits = []
        async def sleep(delay):
            waits.append(delay)
            now[0] += delay
        clock = Clock()
        with patch('media.time.monotonic', side_effect=lambda: now[0]), patch('media.asyncio.sleep', side_effect=sleep):
            self.assertEqual(await clock.tick(.02), 0)
            now[0] += .5
            self.assertAlmostEqual(await clock.tick(.02), .5)
            await clock.tick(.02)
        self.assertGreater(waits[-1], .01, 'the next frame waits instead of replaying a stale backlog')

    async def test_video_timestamps_follow_a_stall(self):
        class Core:
            def video_frame(self):
                return np.zeros((240,320,3), dtype=np.uint8)
        video = GameVideo(Core())
        video.clock.tick = AsyncMock(side_effect=[0, .033, .533])
        vf = [await video.recv() for _ in range(3)]
        self.assertGreater((vf[2].pts-vf[1].pts)/90000, .49)


class FakeCore:
    """An emulator audio queue that the test fills by hand."""
    sample_rate = 44100

    def __init__(self):
        self.pcm = bytearray()

    def audio_queued(self):
        return len(self.pcm)//4

    def audio_frame(self, count):
        result = bytes(self.pcm[:count*4]).ljust(count*4, b'\0')
        del self.pcm[:count*4]
        return result


class AudioPacingTests(IsolatedAsyncioTestCase):
    async def test_waits_for_the_core_instead_of_sending_silence(self):
        core = FakeCore()
        audio = GameAudio(core)
        chunk = np.full(882*2, 7, dtype=np.int16).tobytes()
        async def produce():
            await asyncio.sleep(.03)  # later than one 20 ms period
            core.pcm.extend(chunk)
        asyncio.get_running_loop().create_task(produce())
        frame = await audio.recv()
        self.assertEqual(bytes(frame.planes[0])[:882*4], chunk)

    async def test_timestamps_advance_one_chunk_while_the_core_keeps_up(self):
        core = FakeCore()
        audio = GameAudio(core)
        core.pcm.extend(bytes(882*4*3))
        frames = [await audio.recv() for _ in range(3)]
        self.assertEqual([f.pts for f in frames], [0, 882, 1764])

    async def test_a_stall_sends_silence_and_moves_timestamps_to_wall_time(self):
        core = FakeCore()
        audio = GameAudio(core, stall=.05)
        core.pcm.extend(bytes(882*4))
        first = await audio.recv()
        await asyncio.sleep(.2)
        stalled = await audio.recv()
        self.assertEqual(bytes(stalled.planes[0])[:882*4], bytes(882*4))
        self.assertGreater((stalled.pts-first.pts)/44100, .2)


class QueueTests(TestCase):
    def test_audio_keeps_newest_forty_ms(self):
        core = Emulator(Path('unused'), Path('unused'), Path('unused'), Path('unused'), InputHub())
        pcm = np.arange(4410, dtype=np.int16).repeat(2)
        core._batch(pcm.ctypes.data, 4410)
        self.assertEqual(len(core.audio), 1764*4)
        self.assertEqual(core.audio_frame(1764), pcm[-3528:].tobytes())
        self.assertEqual(core.audio_frame(882), bytes(882*4))

    def test_core_reads_sticks_and_button_pressure(self):
        hub = InputHub(players=2)
        hub.claim('a', 0)
        hub.update('a', 1, 1 | (1 << 13), [-32768, 32767, 1200, -5])
        core = Emulator(Path('unused'), Path('unused'), Path('unused'), Path('unused'), hub)
        core._poll()
        stick = lambda index, axis: core._input(0, 5, index, axis)
        self.assertEqual([stick(0, 0), stick(0, 1), stick(1, 0), stick(1, 1)], [-32768, 32767, 1200, -5])
        self.assertEqual([core._input(0, 5, 2, n) for n in (0, 1, 13)], [32767, 0, 32767], 'pressure of Cross, Square, R2')
        self.assertEqual(core._input(1, 5, 0, 0), 0)
        self.assertEqual(core._input(0, 1, 0, 256), 1 | (1 << 13))

    def test_poll_delay_records_first_poll_only(self):
        hub = InputHub()
        hub.claim('a', 0)
        with patch('inputs.time.monotonic', return_value=1.):
            hub.update('a', 1, 1)
        with patch('inputs.time.monotonic', return_value=1.012):
            hub.snapshot()
        self.assertAlmostEqual(hub.timing('a'), 12)
        with patch('inputs.time.monotonic', return_value=1.2):
            hub.snapshot()
        self.assertAlmostEqual(hub.timing('a'), 12)
        hub.release('a')
        self.assertIsNone(hub.timing('a'))
