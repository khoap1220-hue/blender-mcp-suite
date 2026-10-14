import json

# Test what happens when \0 is appended to json string
s = json.dumps({"type": "ping"}) + "\0"
try:
    json.loads(s)
    print("Parsed successfully with \\0")
except json.JSONDecodeError as e:
    print("JSONDecodeError with \\0:", e)
