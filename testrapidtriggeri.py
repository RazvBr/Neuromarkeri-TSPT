import socket
import time

UDP_IP = "127.0.0.1"
UDP_PORT = 1000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
endpoint = (UDP_IP, UDP_PORT)
codes = [1, 2, 3, 321]
for code in codes:
    code_encoded = str(code).encode()
    sock.sendto(code_encoded, endpoint)
    time.sleep(0.05)   # 50 ms activ
    sock.sendto(b"0", endpoint)
    time.sleep(1.0)

sock.close()
print("Gata.")