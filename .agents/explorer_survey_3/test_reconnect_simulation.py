import socket
import threading
import time
import json

class MockBlenderServer:
    def __init__(self, port=9879):
        self.port = port
        self.running = False
        self.sock = None
        self.thread = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen(5)
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        self.sock.settimeout(0.5)
        while self.running:
            try:
                client, _ = self.sock.accept()
                threading.Thread(target=self._handle, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
            except:
                break

    def _handle(self, client):
        try:
            data = client.recv(4096)
            if data:
                cmd = json.loads(data.decode('utf-8'))
                res = {"status": "success", "result": f"Handled {cmd.get('type')}"}
                client.sendall(json.dumps(res).encode('utf-8'))
        except:
            pass
        finally:
            client.close()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

class ResilientClient:
    def __init__(self, port=9879):
        self.port = port
        self.sock = None

    def connect(self, timeout=1.0):
        try:
            if self.sock:
                self.sock.close()
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect(("127.0.0.1", self.port))
            return True
        except Exception:
            self.sock = None
            return False

    def send_command(self, cmd_type, params=None, max_timeout=3.0):
        """Sends command with auto-reconnect within max_timeout seconds."""
        t_start = time.perf_counter()
        delays = [0.1, 0.2, 0.4, 0.8, 1.0]
        attempt = 0

        while time.perf_counter() - t_start < max_timeout:
            try:
                if not self.sock:
                    if not self.connect(timeout=0.5):
                        delay = delays[min(attempt, len(delays)-1)]
                        time.sleep(delay)
                        attempt += 1
                        continue

                payload = json.dumps({"type": cmd_type, "params": params or {}}).encode('utf-8')
                self.sock.sendall(payload)
                self.sock.settimeout(2.0)
                data = self.sock.recv(4096)
                if not data:
                    raise ConnectionResetError("Server closed connection")
                return json.loads(data.decode('utf-8'))
            except (ConnectionResetError, BrokenPipeError, ConnectionRefusedError, socket.timeout, OSError) as e:
                # Connection dropped or timed out
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass
                    self.sock = None
                delay = delays[min(attempt, len(delays)-1)]
                time.sleep(delay)
                attempt += 1

        raise TimeoutError(f"Auto-reconnect exceeded {max_timeout}s timeout")

# Test simulation:
print("--- Step 1: Start server ---")
srv = MockBlenderServer(9879)
srv.start()

client = ResilientClient(9879)
r1 = client.send_command("ping")
print("Initial call response:", r1)

print("\n--- Step 2: Abruptly kill server ---")
srv.stop()

# Start background thread to simulate Blender restarting 1.2 seconds later
def delayed_restart():
    time.sleep(1.2)
    print("\n[Simulator] Restarting server now...")
    srv.start()

threading.Thread(target=delayed_restart, daemon=True).start()

print("\n--- Step 3: Client calls command while server is restarting ---")
t0 = time.perf_counter()
r2 = client.send_command("test_reconnect", max_timeout=3.0)
elapsed = time.perf_counter() - t0

print(f"Call succeeded! Response: {r2}")
print(f"Elapsed recovery time: {elapsed:.2f}s (< 3.0s: {elapsed < 3.0})")

srv.stop()
