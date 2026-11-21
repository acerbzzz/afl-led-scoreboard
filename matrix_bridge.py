"""Python 2.7/3 compatible raw-frame bridge; no network or app logic here."""
from __future__ import print_function
import sys


def read_exact(stream, count):
    chunks = []
    while count:
        chunk = stream.read(count)
        if not chunk:
            if chunks:
                raise IOError('Incomplete LED frame')
            return None
        chunks.append(chunk)
        count -= len(chunk)
    return b''.join(chunks)


def run(stream, ready, matrix):
    from PIL import Image
    ready.write(b'BOARD_READY\n')
    ready.flush()
    try:
        while True:
            payload = read_exact(stream, 1 + 64 * 32 * 3)
            if payload is None:
                return
            matrix.brightness = ord(payload[:1])
            matrix.SetImage(Image.frombytes('RGB', (64, 32), payload[1:]))
    finally:
        matrix.Clear()


if __name__ == '__main__':
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.hardware_mapping = sys.argv[1]
    options.brightness = int(sys.argv[2])
    options.gpio_slowdown = int(sys.argv[3])
    matrix = RGBMatrix(options=options)
    run(getattr(sys.stdin, 'buffer', sys.stdin),
        getattr(sys.stdout, 'buffer', sys.stdout), matrix)
