import sys, time, serial, argparse

ap = argparse.ArgumentParser()
ap.add_argument('--port', default='COM3')
ap.add_argument('--baud', type=int, default=115200)
ap.add_argument('--log', default='send.log')
ap.add_argument('--capture', type=float, default=60)
ap.add_argument('cmds', nargs='*')
a = ap.parse_args()

ser = serial.Serial(a.port, a.baud, timeout=0.2)
buf = bytearray()


def pump(secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        d = ser.read(4096)
        if d:
            buf += d
            sys.stdout.write(d.decode('latin1', 'replace'))
            sys.stdout.flush()


pump(1.5)
for c in a.cmds:
    ser.write((c + '\r').encode())
    ser.flush()
    pump(1.2)
pump(a.capture)
ser.close()
open(a.log, 'wb').write(bytes(buf))
print('\n[captured %d bytes -> %s]' % (len(buf), a.log))
