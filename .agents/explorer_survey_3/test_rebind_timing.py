import socket
import time

port = 9876
s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s1.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
s1.bind(("127.0.0.1", port))
s1.listen(1)
print("s1 bound")
s1.close()
print("s1 closed")

# Test immediate rebind
t0 = time.perf_counter()
s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s2.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
try:
    s2.bind(("127.0.0.1", port))
    s2.listen(1)
    print(f"s2 rebound immediately in {(time.perf_counter()-t0)*1000:.2f}ms")
    s2.close()
except Exception as e:
    print(f"s2 rebind failed: {e}")
