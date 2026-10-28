"""Be the tracer the macOS core asks for.

The official macOS PCSX ReARMed core calls ptrace(PT_TRACE_ME) in retro_init.
That makes the parent process a debugger: every signal, Ctrl+C included, then
stops the host until the parent resumes it, and a shell never does. On macOS,
run the program as our child and pass each signal on to it.
"""
import ctypes
import os
import platform
import signal
import sys

PT_CONTINUE = 7
CHILD = 'LAN_PARTY_TRACED_CHILD'
# Delivering a job-control stop would only stop the child again.
SUPPRESS = {signal.SIGSTOP, signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU}


def supervise():
    """On macOS, re-run this program as a child we trace. Returns only in the child."""
    if platform.system() != 'Darwin' or os.environ.get(CHILD):
        return
    pid = os.posix_spawn(sys.executable, [sys.executable, *sys.orig_argv[1:]],
                         dict(os.environ, **{CHILD: '1'}))
    # The terminal sends Ctrl+C to the whole process group; the child handles it.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, lambda sig, frame: os.kill(pid, sig))
    libc = ctypes.CDLL(None, use_errno=True)
    while True:
        _, status = os.waitpid(pid, os.WUNTRACED)
        if not os.WIFSTOPPED(status):
            code = os.waitstatus_to_exitcode(status)
            sys.exit(code if code >= 0 else 128-code)
        sig = os.WSTOPSIG(status)
        # Before retro_init the child is not traced yet; resume a plain stop.
        if libc.ptrace(PT_CONTINUE, pid, ctypes.c_void_p(1), 0 if sig in SUPPRESS else sig) != 0:
            os.kill(pid, signal.SIGCONT)
