import sys, time, serial
port = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 45
out = sys.argv[3] if len(sys.argv) > 3 else 'cap.log'
ser = serial.Serial(port, 115200, timeout=0.2)
t0 = time.time()
buf = bytearray()
while time.time() - t0 < secs:
    d = ser.read(4096)
    if d:
        buf += d
ser.close()
open(out, 'wb').write(bytes(buf))
print('captured %d bytes -> %s' % (len(buf), out))
