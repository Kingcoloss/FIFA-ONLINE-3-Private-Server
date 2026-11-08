"""Golden data for FO3.Host, made by the Python server's own code.

Writes into tests/FO3.Host.Tests/Golden/:
  messenger.json  messenger.py's encode() frames for a set of messages, its replies() answers,
                  and the real client's first frame body (captured 2026-10-29)
  pyjson.json     json.dumps text (compact and default separators) and repr() of floats

Run: python dotnetVersion/tools/golden/gen_host_golden.py   (needs `cryptography`)
"""
import json
import math
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(HERE, "..", "..", "tests", "FO3.Host.Tests", "Golden")
sys.path.insert(0, ROOT)
sys.argv = [sys.argv[0]]  # messenger reads its port from argv
import messenger  # noqa: E402

MESSAGES = [
    {"cmd": "auth", "sessionid": ""},
    {"cmd": "auth", "result": True},
    {"cmd": "ping"},
    {"cmd": "sign", "result": True},
    {"cmd": "push", "uri": "/ladder/room", "body": {"roomid": 12, "side": {"left": {"name": "Garuda07"}}}},
    {"cmd": "push", "uri": "/club/chat", "body": {"message": "สวัสดี ครับ", "tag": "<b>&'\"\\/", "ctl": "a\tb\nc\x01\x7f"}},
    {"cmd": "push_all", "list": [1, -2, 3.5, 1e-05, 1e16, None, False, [], {}]},
    {"cmd": "push", "uri": "/emoji", "body": {"s": "\U0001F600 ok"}},
]
CLIENT_FIRST = "8b412a58950cd8431cb7b2e7473b61a8534a576ac50317310d047b5400622951"


def messenger_golden():
    frames = [{"message": m, "frame": messenger.encode(m).hex()} for m in MESSAGES]
    replies = [{"message": m, "replies": messenger.replies(m)}
               for m in ({"cmd": "auth", "sessionid": "x"}, {"cmd": "ping"}, {"cmd": "signon"}, {"cmd": "other"}, {})]
    return {"frames": frames, "replies": replies,
            "client_first": {"body": CLIENT_FIRST, "message": messenger.decode(bytes.fromhex(CLIENT_FIRST))}}


def pyjson_golden():
    r = random.Random(20261108)
    floats = [0.1, 1.5, 100.0, 1e-4, 1e-5, 0.0001234, 1e15, 1e16, 9999999999999998.0, 123456789012345678.0,
              2.5e-7, 1e22, 1e-300, 5e-324, 1.7976931348623157e308, -0.0, -2.75, 3.0, 12345.678, 0.3]
    floats += [r.uniform(-1e6, 1e6) for _ in range(500)] + [r.random() for _ in range(500)]
    floats += [math.ldexp(r.random(), r.randint(-1070, 1020)) for _ in range(1000)]
    floats += [float(r.randint(1, 10**17)) for _ in range(200)]
    docs = [{"coaches": [{"name": "ทดสอบ", "ep": 1500000, "rate": 0.25, "ok": True, "x": None}], "defaultcoachid": "",
             "teams": {"1": {"players": [1, 2, 3], "nested": {"a": [], "b": {}}}}},
            {"s": "a\"b\\c\n\r\t\b\f\x00\x1f~\x7fé€\U0001F600"}, [1, 2.0, -3, "x"], "plain", 7, 2.5, True, None]
    return {"floats": [{"value": f, "repr": repr(f)} for f in floats],
            "docs": [{"doc": d, "compact": json.dumps(d, separators=(",", ":")), "default": json.dumps(d)} for d in docs]}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, data in (("messenger.json", messenger_golden()), ("pyjson.json", pyjson_golden())):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(name, os.path.getsize(os.path.join(OUT, name)), "bytes")


if __name__ == "__main__":
    main()
