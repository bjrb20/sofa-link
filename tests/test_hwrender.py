import ctypes as C
import platform
import unittest

import numpy as np

import hwrender
from emulator import Emulator
from inputs import InputHub
from systems import PROFILES


def request(context_type=hwrender.OPENGL_CORE, version=(3, 2), bottom_left=True):
    callback = hwrender.HWRenderCallback()
    callback.context_type = context_type
    callback.version_major, callback.version_minor = version
    callback.depth = callback.stencil = True
    callback.bottom_left_origin = bottom_left
    return callback


class FrontendTests(unittest.TestCase):
    def test_hardware_frames_are_read_back_into_the_video_pipeline(self):
        emulator = Emulator('core.so', 'game.elf', 'system', 'saves', InputHub(2), profile=PROFILES['ps2-play'])
        class FakeGL:
            def read(self, width, height):
                return np.full((height, width, 3), 7, dtype=np.uint8)
        emulator.hw = FakeGL()
        emulator._video(hwrender.FRAME_VALID, 640, 448, 0)
        self.assertEqual(emulator.video_frame().shape, (448, 640, 3))
        self.assertEqual(int(emulator.video_frame()[0, 0, 0]), 7)
        emulator._video(None, 640, 448, 0)  # a duplicate frame keeps the last picture
        self.assertEqual(int(emulator.video_frame()[0, 0, 0]), 7)
        self.assertIsNone(emulator.callback_error)

    def test_unsupported_contexts_are_declined(self):
        emulator = Emulator('core.so', 'game.elf', 'system', 'saves', InputHub(2), profile=PROFILES['ps2'])
        self.assertFalse(emulator._set_hw_render(request(hwrender.VULKAN, (1, 1))))
        self.assertIsNone(emulator.hw)
        self.assertEqual(hwrender.requested(request(hwrender.VULKAN, (1, 1))), 'Vulkan 1.1')


@unittest.skipUnless(platform.system() == 'Linux', 'offscreen OpenGL uses EGL on Linux')
class OffscreenGLTests(unittest.TestCase):
    def context(self, **kwargs):
        try:
            return hwrender.OffscreenGL(request(**kwargs))
        except RuntimeError as error:
            self.skipTest(f'no headless EGL here: {error}')

    def draw_red_with_green_top(self, gl):
        """Clear red, then green over the upper GL half (rows 16-31 counted from the bottom)."""
        proc = gl.egl.eglGetProcAddress
        clear_color = C.CFUNCTYPE(None, C.c_float, C.c_float, C.c_float, C.c_float)(proc(b'glClearColor'))
        clear = C.CFUNCTYPE(None, C.c_uint)(proc(b'glClear'))
        enable = C.CFUNCTYPE(None, C.c_uint)(proc(b'glEnable'))
        scissor = C.CFUNCTYPE(None, C.c_int, C.c_int, C.c_int, C.c_int)(proc(b'glScissor'))
        gl.gl.glBindFramebuffer(hwrender.GL_FRAMEBUFFER, gl.get_current_framebuffer())
        clear_color(1, 0, 0, 1)
        clear(0x4000)
        enable(0x0C11)  # GL_SCISSOR_TEST
        scissor(0, 16, 64, 16)
        clear_color(0, 1, 0, 1)
        clear(0x4000)

    def test_core_frame_is_read_back_top_row_first(self):
        gl = self.context()
        try:
            gl.resize(128, 64)
            self.assertTrue(gl.get_current_framebuffer())
            self.assertTrue(gl.get_proc_address(b'glDrawArrays'))
            self.draw_red_with_green_top(gl)
            frame = gl.read(64, 32)  # the core used only part of its framebuffer
            self.assertEqual(frame.shape, (32, 64, 3))
            self.assertEqual(frame[0, 0].tolist(), [0, 255, 0])
            self.assertEqual(frame[-1, -1].tolist(), [255, 0, 0])
        finally:
            gl.close()

    def test_top_left_origin_core_is_not_flipped(self):
        gl = self.context(bottom_left=False)
        try:
            gl.resize(64, 32)
            self.draw_red_with_green_top(gl)
            self.assertEqual(gl.read(64, 32)[0, 0].tolist(), [255, 0, 0])
        finally:
            gl.close()


if __name__ == '__main__':
    unittest.main()
