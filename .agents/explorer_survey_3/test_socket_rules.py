import socket
import sys

def test_port_availability(port=9876):
    print(f"--- 1. Testing port {port} availability ---")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", port))
        print(f"Port {port} is currently OPEN and listening (connected successfully).")
        s.close()
        return False
    except ConnectionRefusedError:
        print(f"Port {port} is FREE (Connection refused).")
        return True
    except Exception as e:
        print(f"Port {port} check result: {e}")
        return False

def test_windows_socket_binding(port=9876):
    print(f"\n--- 2. Testing socket binding rules on Windows ---")
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s1.bind(("127.0.0.1", port))
    s1.listen(1)
    print(f"Socket 1 bound to 127.0.0.1:{port} with SO_REUSEADDR=1")

    # Test what happens if socket 2 tries to bind to the same port on Windows
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s2.bind(("127.0.0.1", port))
        print("WARNING: Socket 2 ALSO bound successfully with SO_REUSEADDR=1! (Windows allows duplicate bind if SO_EXCLUSIVEADDRUSE is not set)")
        s2.close()
    except Exception as e:
        print(f"Socket 2 bind failed as expected: {e}")

    # Now close s1 and test rapid rebind
    s1.close()
    print("Socket 1 closed.")

    s3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s3.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s3.bind(("127.0.0.1", port))
        s3.listen(1)
        print("Socket 3 successfully rebound immediately to 127.0.0.1:9876.")
        s3.close()
    except Exception as e:
        print(f"Socket 3 rebind failed: {e}")

def test_localhost_vs_all_interfaces(port=9876):
    print(f"\n--- 3. Testing 127.0.0.1 vs 0.0.0.0 vs 'localhost' ---")
    for host in ["127.0.0.1", "localhost", "0.0.0.0"]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            s.listen(1)
            print(f"Binding to ({host}, {port}) -> SUCCESS")
            s.close()
        except Exception as e:
            print(f"Binding to ({host}, {port}) -> FAILED: {e}")

if __name__ == "__main__":
    test_port_availability(9876)
    test_windows_socket_binding(9876)
    test_localhost_vs_all_interfaces(9876)
