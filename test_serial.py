import serial
import time

ser = serial.Serial('COM3', 115200, timeout=2)
time.sleep(2)

# Clear buffer
ser.reset_input_buffer()

# Wait 3 seconds after boot
time.sleep(3)

# Read everything available right now
data = ser.read_all()
print("=== RAW BYTES ===")
print(repr(data))
print("\n=== DECODED ===")
print(data.decode('utf-8', errors='replace'))

ser.close()
