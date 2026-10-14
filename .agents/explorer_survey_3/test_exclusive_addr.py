import socket

port = 9876
s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# SO_EXCLUSIVEADDRUSE is -5 on Windows (socket.SO_EXCLUSIVEADDRUSE)
s1.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
s1.bind(("127.0.0.1", port))
s1.listen(1)
print("Socket 1 bound with SO_EXCLUSIVEADDRUSE=1")

s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s2.bind(("127.0.0.1", port))
    print("Socket 2 bound unexpectedly!")
except OSError as e:
    print(f"Socket 2 bind failed with expected error: {e}")

s1.close()
s2.close()
