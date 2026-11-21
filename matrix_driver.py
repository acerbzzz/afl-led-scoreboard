"""Reuse either the installed Python 3 binding or a legacy Python 2 binding."""
import os
from pathlib import Path
import select
import subprocess
import time


class LegacyMatrix:
    def __init__(self, args, python):
        self._brightness = args.brightness
        self._last_image = None
        self.process = subprocess.Popen(
            [python, str(Path(__file__).with_name('matrix_bridge.py')),
             args.mapping, str(args.brightness), str(args.gpio_slowdown)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        try:
            deadline = time.monotonic() + 20
            response = b''
            while time.monotonic() < deadline:
                if select.select([self.process.stdout], [], [], .2)[0]:
                    char = os.read(self.process.stdout.fileno(), 1)
                    if not char:
                        break
                    response = (response + char)[-1024:]
                    if response.endswith(b'BOARD_READY\n'):
                        os.set_blocking(self.process.stdin.fileno(), False)
                        return
            raise RuntimeError('Legacy LED driver did not start; see the error above.')
        except BaseException:
            self.Clear()
            raise

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        value = max(1, min(100, int(value)))
        if value != self._brightness:
            self._brightness = value
            if self._last_image is not None:
                self.SetImage(self._last_image)

    def SetImage(self, image):
        if image.size != (64, 32):
            raise ValueError('LED frame must be 64 x 32')
        self._last_image = image.copy()
        data = bytes([self._brightness]) + image.convert('RGB').tobytes()
        deadline = time.monotonic() + 5
        while data:
            if self.process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Legacy LED driver stopped responding')
            if select.select([], [self.process.stdin], [], .2)[1]:
                try:
                    count = os.write(self.process.stdin.fileno(), data)
                    data = data[count:]
                except BlockingIOError:
                    pass

    def Clear(self):
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if self.process.stdout:
            self.process.stdout.close()


def make_matrix(args):
    legacy = os.environ.get('BOARD_LEGACY_PYTHON')
    if legacy:
        return LegacyMatrix(args, legacy)
    from afl_scoreboard import make_matrix as native_matrix
    return native_matrix(args)
