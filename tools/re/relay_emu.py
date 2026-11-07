"""FO3 relay emulator (experiment). Packet = u16 checksum | u16 key | 30+ bytes payload, where the
payload (RE of fifazf 0xa65640 / 0xa651b0) is rotated by the key and chained-XOR'd:
  enc: out[i] = pay[(k+i) % n]; c[i] = (out[i] + dl) ^ c[i-1], c[-1] = k >> 8, dl = (k>>8)+(k&0xff)
  checksum: h = 0x17; h = h*0x103 + b over bytes [2:]
Plain header (24 bytes incl. checksum/key): [4] i8 src slot, [5] i8 dst slot (-1 any),
[6:10] u32 matchid, [0xa:0xe] u32 reliable seq / sub-message count, [0xe:0x12] u32 cumulative
ack, [0x12:0x16] u32 token, [0x16:0x18] u16 type (see header()).
0x4005 = ping {u32 sender ts, u32 ip, u16 port}, answered by 0x4006 pong with the same body
(receive switch 0xa66c40 indexes type - 0x4001; the pong sets the slot's connected flag).
Usage: python relay_emu.py <port> <log>"""
import random, socket, struct, sys, time

RELAY_SLOT = 0x14


def checksum(b):
    h = 0x17
    for x in b:
        h = (h * 0x103 + x) & 0xffff
    return h


def decrypt(p):
    k = int.from_bytes(p[2:4], "little"); n = len(p) - 4
    dl = ((k >> 8) + (k & 0xff)) & 0xff
    prev, r = p[3], []
    for x in p[4:]:
        r.append(((x ^ prev) - dl) & 0xff); prev = x
    pay = [0] * n
    for i in range(n):
        pay[(k + i) % n] = r[i]
    return p[:4] + bytes(pay)


def encrypt(plain, k=None):
    """plain: 24-byte header (first 4 bytes ignored) + body."""
    k = k or random.randint(1, 0xffff); pay = plain[4:]; n = len(pay)
    dl = ((k >> 8) + (k & 0xff)) & 0xff
    out = [pay[(k + i) % n] for i in range(n)]
    prev, c = k >> 8, []
    for x in out:
        prev = ((x + dl) & 0xff) ^ prev; c.append(prev)
    rest = struct.pack("<H", k) + bytes(c)
    return struct.pack("<H", checksum(rest)) + rest


def header(src, dst, mid, ack, typ, rseq=0, token=0):
    """[0xa] reliable seq (type 1) / sub-message count (type 2), [0xe] cumulative ack = highest
    contiguous reliable seq received from the addressee (0 = none; seqs start at 1),
    [0x12] the token the addressee gave us (relay message 0x100)."""
    return b"\0" * 4 + struct.pack("<bbIIIIH", src, dst, mid, rseq, ack, token, typ)


class Client:
    """Reliable stream state of one client as seen by the relay. Reliable data comes as type 1
    {[0xa] seq, chunk} or type 2 {u8 compressed, [0xa] count x (u32 seq, u16 len, chunk)}; the
    chunks in seq order form a stream of messages {u16 body len, u16 msgid, body} (the
    TcpPacket of fifazf 0xa682b0, cut in 400-byte chunks)."""

    def __init__(self):
        self.ack, self.got, self.stream, self.seq, self.out = 0, {}, b"", 0, {}

    def take(self, m):
        """Fold one decoded packet in; return the completed (msgid, body) messages."""
        for q in [q for q in self.out if q <= m["ack"]]:  # the client's ack of our messages
            del self.out[q]
        subs = []
        if m["type"] == 1:
            subs = [(m["rseq"], m["body"])]
        elif m["type"] in (2, 0x4001, 0x4004) and m["body"] and m["body"][0] == 0:  # 0x4001: ack me
            p = 1
            for _ in range(m["rseq"]):  # the sub-message count
                if p + 6 > len(m["body"]):
                    break
                q, n = struct.unpack_from("<IH", m["body"], p)
                subs.append((q, m["body"][p + 6:p + 6 + n])); p += 6 + n
        for q, chunk in subs:
            if q > self.ack:
                self.got.setdefault(q, chunk)
        while self.ack + 1 in self.got:
            self.ack += 1
            self.stream += self.got.pop(self.ack)
        msgs = []
        while len(self.stream) >= 4:
            n, msgid = struct.unpack_from("<HH", self.stream)
            if len(self.stream) < 4 + n:
                break
            msgs.append((msgid, self.stream[4:4 + n])); self.stream = self.stream[4 + n:]
        return msgs

    def queue(self, msgid, body=b""):
        self.seq += 1
        self.out[self.seq] = struct.pack("<HH", len(body), msgid) + body


def parse(plain):
    src, dst, mid, rseq, ack, token, typ = struct.unpack_from("<bbIIIIH", plain, 4)
    return dict(src=src, dst=dst, mid=mid, rseq=rseq, ack=ack, token=token, type=typ, body=plain[24:])


def selftest():
    p = bytes.fromhex("7b7d2a002a002a002a002f4517341e349db79db622b59fa1ef97eab399b399b399b3")
    plain = decrypt(p)
    assert encrypt(plain, int.from_bytes(p[2:4], "little")) == p
    m = parse(plain)
    assert m["type"] == 0x4005 and m["dst"] == RELAY_SLOT and m["mid"] == 793988644, m
    join = struct.pack("<HHIBBB", 7, 0x100, 793988644, 2, 0, 3)  # split over two chunks
    agg = b"\0" + struct.pack("<IH", 2, 5) + join[6:] + struct.pack("<IH", 1, 6) + join[:6]
    c = Client()
    assert c.take(dict(type=2, rseq=2, ack=0, body=agg)) == [(0x100, join[4:])] and c.ack == 2
    c.queue(0x101)
    assert c.take(dict(type=2, rseq=0, ack=1, body=b"\0")) == [] and not c.out
    assert c.take(dict(type=2, rseq=3, ack=1, body=b"\0")) == []  # a count past the body
    print("relay_emu selftest OK")


def main(port, log):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", port))

    def note(line):
        with open(log, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
    note(f"relay emu on udp {port}")
    clients = {}
    while True:
        try:
            data, addr = s.recvfrom(65536)
        except ConnectionResetError:  # Windows: ICMP port unreachable from an earlier send
            continue
        if len(data) < 24 or checksum(data[2:]) != int.from_bytes(data[:2], "little"):
            note(f"{addr} bad {data.hex()}"); continue
        m = parse(decrypt(data))
        c = clients.setdefault(addr, Client())
        if m["type"] not in (0x4005, 0x4006):
            note(f"{addr} <- src {m['src']} dst {m['dst']} mid {m['mid']} rseq {m['rseq']} ack {m['ack']} "
                 f"token {m['token']} type {m['type']:#06x} body {m['body'].hex()}")
        for msgid, body in c.take(m):
            note(f"{addr} <- msg {msgid:#06x} {body.hex()}")
            if msgid == 0x100:  # JOIN {u32 matchid, u8 users, u8 slot, u8 flag}: token, then inited
                c.queue(0x100, struct.pack("<I", 1))
                c.queue(0x101)
        if m["type"] == 0x4005:  # ping -> pong with the same body (the client's own handler does
            # that); the pong marks the relay slot connected (0xa66f5e)
            s.sendto(encrypt(header(RELAY_SLOT, m["src"], m["mid"], c.ack, 0x4006) + m["body"]), addr)
        if m["type"] == 0x4001:  # reliable aggregate that wants an ack: 0x4002, empty body
            s.sendto(encrypt(header(RELAY_SLOT, m["src"], m["mid"], c.ack, 0x4002)), addr)
        for q, msg in sorted(c.out.items()):  # (re)send what the client has not acked
            s.sendto(encrypt(header(RELAY_SLOT, m["src"], m["mid"], c.ack, 1, rseq=q) + msg), addr)
            note(f"{addr} -> seq {q} msg {msg.hex()}")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main(int(sys.argv[1]), sys.argv[2])
