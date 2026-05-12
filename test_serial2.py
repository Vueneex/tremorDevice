import serial
import time

# Close and reopen
try:
    s = serial.Serial('COM3')
    s.close()
    time.sleep(1)
except:
    pass

ser = serial.Serial('COM3', 115200, timeout=2)
time.sleep(3)

data = ser.read_all()
print('=== RAW ===')
print(repr(data))
print('=== DECODED ===')
print(data.decode('utf-8', errors='replace'))

ser.close()
