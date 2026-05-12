import subprocess
import time

# Kill any st-util processes
subprocess.run(['taskkill', '/F', '/IM', 'st-util.exe'], capture_output=True)
time.sleep(1)

# Reset via STLink - power cycle simulation
print("Resetting STM32...")
subprocess.run(['mode', 'COM3:', 'BAUD=115200', 'DATA=8', 'STOP=1', 'PARITY=N'], capture_output=True)
time.sleep(2)

# Now read
import serial
ser = serial.Serial('COM3', 115200, timeout=2)
time.sleep(3)
data = ser.read_all()
print('=== OUTPUT ===')
print(repr(data))
print(data.decode('utf-8', errors='replace'))
ser.close()
