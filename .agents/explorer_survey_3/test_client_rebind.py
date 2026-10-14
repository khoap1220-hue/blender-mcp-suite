import socket
import time

port = 9876
s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s1.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
s1.bind(("127.0.0.1", port))
s1.listen(1)

# Connect client
c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
c.connect(("127.0.0.1", port))
srv_c, addr = s1.accept()

# Now srv_c and c are connected.
# Let s1 close listening socket, and close srv_c
srv_c.shutdown(socket.SHUT_RDWR)
srv_c.close()
s1.close()

# Now c is closed
c.close()

# Try rebind
s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s2.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
try:
    s2.bind(("127.0.0.1", port))
    s2.listen(1)
    print("SUCCESS: Rebound immediately even after client connection cycle!")
    s2.close()
except Exception as e:
    print(f"Rebind failed: {e}")
