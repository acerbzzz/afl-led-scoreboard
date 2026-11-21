"""Regression checks for legacy frames, recovery and phone-controlled channels."""
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import Request, urlopen
from PIL import Image
from matrix_bridge import read_exact, run
from matrix_driver import LegacyMatrix
from types import SimpleNamespace


class BridgeTests(unittest.TestCase):
    def test_fragmented_frames_brightness_and_eof(self):
        class ShortReads(io.BytesIO):
            def read(self, count):
                return super().read(min(count, 7))
        class Matrix:
            brightness = 0
            def SetImage(self, frame):
                self.received = (self.brightness, frame.getpixel((0, 0)))
            def Clear(self):
                self.cleared = True
        matrix = Matrix()
        stream = ShortReads(bytes([12]) + Image.new('RGB', (64, 32), 'red').tobytes())
        ready = io.BytesIO()
        run(stream, ready, matrix)
        self.assertEqual(matrix.received, (12, (255, 0, 0)))
        self.assertEqual(ready.getvalue(), b'BOARD_READY\n')
        self.assertTrue(matrix.cleared)
        with self.assertRaises(IOError):
            read_exact(io.BytesIO(b'ab'), 3)

    def test_legacy_process_and_brightness_without_new_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'rgbmatrix.py').write_text('''import os
class RGBMatrixOptions: pass
class RGBMatrix:
    def __init__(self, options): pass
    def SetImage(self, image):
        with open(os.environ['TEST_FRAMES'], 'a') as f:
            f.write(str(self.brightness) + '\\n')
    def Clear(self): pass
''')
            old = os.environ.copy()
            os.environ['PYTHONPATH'] = folder + os.pathsep + old.get('PYTHONPATH', '')
            os.environ['TEST_FRAMES'] = str(path/'frames')
            try:
                matrix = LegacyMatrix(SimpleNamespace(brightness=20, mapping='regular', gpio_slowdown=2), sys.executable)
                matrix.SetImage(Image.new('RGB',(64,32),'red'))
                matrix.brightness = 12
                matrix.Clear()
                self.assertEqual((path/'frames').read_text().splitlines(), ['20','12'])
            finally:
                os.environ.clear()
                os.environ.update(old)


class PhoneTests(unittest.TestCase):
    def test_corrupt_settings_then_switch_all_channels_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'settings.json').write_text('{interrupted')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            url = 'http://127.0.0.1:%d' % port
            command = [sys.executable, 'board.py', '--data', folder, '--port', str(port)]
            log = open(path/'log', 'w')
            proc = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
            def get():
                with urlopen(url+'/api', timeout=2) as response:
                    return json.load(response)
            def wait(sport=None):
                for _ in range(120):
                    if proc.poll() is not None:
                        self.fail((path/'log').read_text())
                    try:
                        result=get()
                        if result.get('ready') and (sport is None or result['state']['sport']==sport):
                            return result
                    except OSError:
                        pass
                    time.sleep(.1)
                self.fail('Display not ready: '+(path/'log').read_text())
            def cleanup():
                import signal
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
            try:
                result=wait()
                self.assertEqual(result['state']['sport'], 'AFL')
                for sport in result['channels']:
                    request=Request(url+'/api', data=json.dumps({'sport':sport,'mode':'Demo'}).encode(),
                                    headers={'X-Board-Key':result['token']})
                    with urlopen(request,timeout=2) as response:
                        self.assertEqual(response.status,200)
                    result=wait(sport)
                    with urlopen(url+'/panel.png',timeout=2) as response:
                        frame=Image.open(io.BytesIO(response.read()))
                        self.assertEqual(frame.size,(64,32))
                        self.assertIsNotNone(frame.getbbox())
                cleanup()
                proc=subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
                self.assertEqual(wait()['state']['sport'],result['state']['sport'])
            finally:
                cleanup()
                log.close()


if __name__ == '__main__':
    unittest.main()
