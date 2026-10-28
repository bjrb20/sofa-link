"""Offscreen OpenGL for hardware-rendered libretro cores; frames are read back to RGB.

The core draws into a framebuffer object that we own. Each frame is copied to
host memory with glReadPixels, so the existing video pipeline stays unchanged.
Linux only: the context comes from EGL without a window (Mesa's surfaceless
platform, or a GPU's EGL device platform).
"""
import ctypes as C
import ctypes.util
import logging

import numpy as np

log = logging.getLogger(__name__)

# retro_hw_context_type
OPENGL, OPENGLES2, OPENGL_CORE, OPENGLES3, OPENGLES_VERSION, VULKAN = 1, 2, 3, 4, 5, 6
CONTEXT_NAMES = {0: 'none', OPENGL: 'OpenGL', OPENGLES2: 'OpenGL ES 2', OPENGL_CORE: 'OpenGL core',
                 OPENGLES3: 'OpenGL ES 3', OPENGLES_VERSION: 'OpenGL ES', VULKAN: 'Vulkan', 7: 'Direct3D'}
FRAME_VALID = C.c_void_p(-1).value  # RETRO_HW_FRAME_BUFFER_VALID

RESET = C.CFUNCTYPE(None)
GET_FRAMEBUFFER = C.CFUNCTYPE(C.c_size_t)
GET_PROC = C.CFUNCTYPE(C.c_void_p, C.c_char_p)


class HWRenderCallback(C.Structure):
    _fields_ = [('context_type', C.c_int), ('context_reset', C.c_void_p),
                ('get_current_framebuffer', GET_FRAMEBUFFER), ('get_proc_address', GET_PROC),
                ('depth', C.c_bool), ('stencil', C.c_bool), ('bottom_left_origin', C.c_bool),
                ('version_major', C.c_uint), ('version_minor', C.c_uint), ('cache_context', C.c_bool),
                ('context_destroy', C.c_void_p), ('debug_context', C.c_bool)]


# EGL and GL enums used below.
EGL_NONE, EGL_SURFACE_TYPE, EGL_RENDERABLE_TYPE = 0x3038, 0x3033, 0x3040
EGL_OPENGL_BIT, EGL_OPENGL_ES2_BIT, EGL_OPENGL_ES3_BIT = 0x8, 0x4, 0x40
EGL_OPENGL_API, EGL_OPENGL_ES_API = 0x30A2, 0x30A0
EGL_CONTEXT_MAJOR_VERSION, EGL_CONTEXT_MINOR_VERSION = 0x3098, 0x30FB
EGL_CONTEXT_OPENGL_PROFILE_MASK, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT = 0x30FD, 0x1
EGL_CONTEXT_OPENGL_COMPATIBILITY_PROFILE_BIT = 0x2
EGL_PLATFORM_SURFACELESS_MESA, EGL_PLATFORM_DEVICE_EXT = 0x31DD, 0x313F
GL_FRAMEBUFFER, GL_RENDERBUFFER, GL_COLOR_ATTACHMENT0 = 0x8D40, 0x8D41, 0x8CE0
GL_DEPTH_ATTACHMENT, GL_DEPTH_STENCIL_ATTACHMENT, GL_FRAMEBUFFER_COMPLETE = 0x8D00, 0x821A, 0x8CD5
GL_RGBA8, GL_DEPTH24_STENCIL8, GL_DEPTH_COMPONENT24 = 0x8058, 0x88F0, 0x81A6
GL_RGBA, GL_UNSIGNED_BYTE, GL_PACK_ALIGNMENT, GL_READ_FRAMEBUFFER = 0x1908, 0x1401, 0x0D05, 0x8CA8


def requested(callback):
    """Describe a core's SET_HW_RENDER request, e.g. 'OpenGL core 3.3'."""
    name = CONTEXT_NAMES.get(callback.context_type, f'type {callback.context_type}')
    if callback.version_major:
        name += f' {callback.version_major}.{callback.version_minor}'
    return name


def supported(context_type):
    return context_type in (OPENGL, OPENGLES2, OPENGL_CORE, OPENGLES3, OPENGLES_VERSION)


class OffscreenGL:
    """One EGL context and framebuffer; every call must run on the core's thread."""

    def __init__(self, callback):
        self.context_type = callback.context_type
        self.version = (callback.version_major, callback.version_minor)
        self.depth, self.stencil = callback.depth, callback.stencil
        self.bottom_left = callback.bottom_left_origin
        self.size = (0, 0)
        self.fbo = 0
        self.egl = self._library('EGL', 'libEGL.so.1')
        e = self.egl
        e.eglGetProcAddress.argtypes, e.eglGetProcAddress.restype = [C.c_char_p], C.c_void_p
        for name in ('eglGetDisplay', 'eglCreateContext', 'eglGetCurrentContext'):
            getattr(e, name).restype = C.c_void_p
        e.eglGetDisplay.argtypes = [C.c_void_p]
        e.eglInitialize.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
        e.eglBindAPI.argtypes = [C.c_uint]
        e.eglChooseConfig.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_void_p), C.c_int, C.POINTER(C.c_int)]
        e.eglCreateContext.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
        e.eglMakeCurrent.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
        e.eglDestroyContext.argtypes = [C.c_void_p, C.c_void_p]
        e.eglTerminate.argtypes = [C.c_void_p]
        e.eglQueryString.argtypes, e.eglQueryString.restype = [C.c_void_p, C.c_int], C.c_char_p
        self.display = self._display()
        self.context = self._context()
        gl = self._gl_functions()
        self.gl = gl
        self.get_proc_address = GET_PROC(self._proc)
        self.get_current_framebuffer = GET_FRAMEBUFFER(lambda: self.fbo)
        renderer = C.cast(gl.glGetString(0x1F01), C.c_char_p).value or b'?'
        version = C.cast(gl.glGetString(0x1F02), C.c_char_p).value or b'?'
        self.renderer = f'{renderer.decode(errors="replace")} ({version.decode(errors="replace")})'
        log.info('Offscreen GL context: %s', self.renderer)

    @staticmethod
    def _library(name, fallback):
        path = ctypes.util.find_library(name) or fallback
        try:
            return C.CDLL(path)
        except OSError as error:
            raise RuntimeError(f'This core needs OpenGL, but {fallback} could not be loaded. '
                               'Install the Mesa EGL/GL packages or a GPU driver.') from error

    def _display(self):
        e = self.egl
        platform = e.eglGetProcAddress(b'eglGetPlatformDisplayEXT')
        candidates = []
        if platform:
            get_platform = C.CFUNCTYPE(C.c_void_p, C.c_uint, C.c_void_p, C.POINTER(C.c_int))(platform)
            candidates.append(lambda: get_platform(EGL_PLATFORM_SURFACELESS_MESA, None, None))
            query = e.eglGetProcAddress(b'eglQueryDevicesEXT')
            if query:
                devices = (C.c_void_p * 8)()
                count = C.c_int()
                if C.CFUNCTYPE(C.c_bool, C.c_int, C.c_void_p, C.POINTER(C.c_int))(query)(8, devices, C.byref(count)):
                    candidates += [lambda d=d: get_platform(EGL_PLATFORM_DEVICE_EXT, d, None)
                                   for d in devices[:count.value]]
        candidates.append(lambda: e.eglGetDisplay(None))
        for candidate in candidates:
            display = candidate()
            if display and e.eglInitialize(display, None, None):
                return display
        raise RuntimeError('No headless EGL display is available for the OpenGL core')

    def _context(self):
        e = self.egl
        es = self.context_type in (OPENGLES2, OPENGLES3, OPENGLES_VERSION)
        major, minor = self.version
        if self.context_type == OPENGLES2:
            major, minor = 2, 0
        elif self.context_type == OPENGLES3:
            major, minor = max(major, 3), minor
        if not e.eglBindAPI(EGL_OPENGL_ES_API if es else EGL_OPENGL_API):
            raise RuntimeError('EGL could not select the OpenGL API')
        renderable = (EGL_OPENGL_ES3_BIT if major >= 3 else EGL_OPENGL_ES2_BIT) if es else EGL_OPENGL_BIT
        attributes = (C.c_int * 5)(EGL_SURFACE_TYPE, 0, EGL_RENDERABLE_TYPE, renderable, EGL_NONE)
        config, count = C.c_void_p(), C.c_int()
        if not e.eglChooseConfig(self.display, attributes, C.byref(config), 1, C.byref(count)) or not count.value:
            raise RuntimeError('EGL has no surfaceless configuration for this core')
        context_attributes = [EGL_CONTEXT_MAJOR_VERSION, major or (2 if es else 1), EGL_CONTEXT_MINOR_VERSION, minor]
        if not es:
            profile = (EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT if self.context_type == OPENGL_CORE
                       else EGL_CONTEXT_OPENGL_COMPATIBILITY_PROFILE_BIT)
            context_attributes += [EGL_CONTEXT_OPENGL_PROFILE_MASK, profile]
        context_attributes.append(EGL_NONE)
        context = e.eglCreateContext(self.display, config, None, (C.c_int * len(context_attributes))(*context_attributes))
        if not context:
            raise RuntimeError(f'EGL could not create a {CONTEXT_NAMES[self.context_type]} {major}.{minor} context')
        if not e.eglMakeCurrent(self.display, None, None, context):
            raise RuntimeError('EGL could not make the OpenGL context current without a surface')
        return context

    def _gl_functions(self):
        class GL:
            pass
        gl = GL()
        signatures = {
            'glGetString': ([C.c_uint], C.c_void_p),
            'glGenFramebuffers': ([C.c_int, C.POINTER(C.c_uint)], None),
            'glDeleteFramebuffers': ([C.c_int, C.POINTER(C.c_uint)], None),
            'glBindFramebuffer': ([C.c_uint, C.c_uint], None),
            'glGenRenderbuffers': ([C.c_int, C.POINTER(C.c_uint)], None),
            'glDeleteRenderbuffers': ([C.c_int, C.POINTER(C.c_uint)], None),
            'glBindRenderbuffer': ([C.c_uint, C.c_uint], None),
            'glRenderbufferStorage': ([C.c_uint, C.c_uint, C.c_int, C.c_int], None),
            'glFramebufferRenderbuffer': ([C.c_uint, C.c_uint, C.c_uint, C.c_uint], None),
            'glCheckFramebufferStatus': ([C.c_uint], C.c_uint),
            'glPixelStorei': ([C.c_uint, C.c_int], None),
            'glReadPixels': ([C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            address = self.egl.eglGetProcAddress(name.encode())
            if not address:
                raise RuntimeError(f'OpenGL function {name} is unavailable')
            setattr(gl, name, C.CFUNCTYPE(result, *args)(address))
        return gl

    def _proc(self, name):
        try:
            return self.egl.eglGetProcAddress(name)
        except Exception:
            return None

    def resize(self, width, height):
        """(Re)create the core's framebuffer at the core's maximum geometry."""
        if (width, height) == self.size:
            return
        gl = self.gl
        self._release()
        fbo, color, depth = C.c_uint(), C.c_uint(), C.c_uint()
        gl.glGenFramebuffers(1, C.byref(fbo))
        gl.glBindFramebuffer(GL_FRAMEBUFFER, fbo.value)
        gl.glGenRenderbuffers(1, C.byref(color))
        gl.glBindRenderbuffer(GL_RENDERBUFFER, color.value)
        gl.glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA8, width, height)
        gl.glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, color.value)
        self.renderbuffers = [color.value]
        if self.depth:
            gl.glGenRenderbuffers(1, C.byref(depth))
            gl.glBindRenderbuffer(GL_RENDERBUFFER, depth.value)
            gl.glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8 if self.stencil else GL_DEPTH_COMPONENT24,
                                     width, height)
            gl.glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT if self.stencil
                                         else GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth.value)
            self.renderbuffers.append(depth.value)
        status = gl.glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f'The offscreen framebuffer is incomplete (0x{status:x})')
        self.fbo, self.size = fbo.value, (width, height)

    def read(self, width, height):
        """Copy the core's latest frame (width x height) to an RGB array, top row first."""
        width, height = min(width, self.size[0]), min(height, self.size[1])
        pixels = np.empty((height, width, 4), dtype=np.uint8)
        gl = self.gl
        gl.glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        gl.glPixelStorei(GL_PACK_ALIGNMENT, 1)
        gl.glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, pixels.ctypes.data)
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        rgb = pixels[:, :, :3]
        # glReadPixels returns the bottom row first. A core with a top-left
        # origin drew its frame upside down, so its rows are already in order.
        return np.ascontiguousarray(rgb[::-1] if self.bottom_left else rgb)

    def _release(self):
        if self.fbo:
            renderbuffers = (C.c_uint * len(self.renderbuffers))(*self.renderbuffers)
            self.gl.glDeleteRenderbuffers(len(self.renderbuffers), renderbuffers)
            self.gl.glDeleteFramebuffers(1, C.byref(C.c_uint(self.fbo)))
            self.fbo, self.size = 0, (0, 0)

    def close(self):
        self._release()
        self.egl.eglMakeCurrent(self.display, None, None, None)
        self.egl.eglDestroyContext(self.display, self.context)
        self.egl.eglTerminate(self.display)
