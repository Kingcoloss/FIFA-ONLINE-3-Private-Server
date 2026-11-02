"""EALayer3 v2 (EAAC codec 6) <-> MPEG-1 Layer III, for the EA Trax music bank.

An EALayer3 v2 frame holds ONE granule of an MP3 frame: a 16-bit frame header (extended, stereo,
2 reserved, 12-bit frame size in bytes; extended adds offset mode 2, offset samples 10, PCM
samples 10, common size 10 bits), then the "common" part: version 2, sample rate 2, channel
mode 2, mode extension 2, granule index 1, scfsi 4 per channel (granule 1 of MPEG-1 only),
per channel the MPEG side info of that granule (part2_3_length 12 + 47 bits for MPEG-1), then
each channel's main data (part2_3_length bits), zero-padded to a byte; an extended frame ends
with its PCM samples (s16be). No bit reservoir: each granule's main data is in its own frame.
Layout from vgmstream (mpeg_custom_utils_ealayer3.c), checked against the game's own tracks.

    python -I tools/re/ealayer3.py check <sps stream file> [out.mp3]   (EA stream -> MP3)
"""
import struct, sys


class Bits:
    """MSB-first bit reader."""

    def __init__(self, data, pos=0):
        self.d, self.p = data, pos

    def read(self, n):
        v = 0
        for _ in range(n):
            v = v << 1 | (self.d[self.p >> 3] >> (7 - (self.p & 7)) & 1)
            self.p += 1
        return v


class Writer:
    """MSB-first bit writer."""

    def __init__(self):
        self.out, self.acc, self.n = bytearray(), 0, 0

    def write(self, v, n):
        for i in range(n - 1, -1, -1):
            self.acc = self.acc << 1 | (v >> i & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc = self.n = 0

    def copy(self, data, start, nbits):
        r = Bits(data, start)
        while nbits >= 24:
            self.write(r.read(24), 24)
            nbits -= 24
        self.write(r.read(nbits), nbits)

    def bytes(self):
        return bytes(self.out) + (bytes([self.acc << (8 - self.n)]) if self.n else b"")


def mp3_frames(mp3):
    """Yield (header u32, side info, main data) of each MPEG-1 Layer III frame (no CRC)."""
    i = 0
    if mp3[:3] == b"ID3":
        i = 10 + ((mp3[6] & 0x7F) << 21 | (mp3[7] & 0x7F) << 14 | (mp3[8] & 0x7F) << 7 | mp3[9] & 0x7F)
    kbps = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
    while i + 4 <= len(mp3):
        h = struct.unpack_from(">I", mp3, i)[0]
        if h >> 21 != 0x7FF or h >> 12 & 15 in (0, 15):
            i += 1
            continue
        assert h >> 19 & 3 == 3 and h >> 17 & 3 == 1 and h >> 16 & 1, "MPEG-1 Layer III without CRC only"
        size = 144000 * kbps[h >> 12 & 15] // [44100, 48000, 32000][h >> 10 & 3] + (h >> 9 & 1)
        side = 17 if (h >> 6 & 3) == 3 else 32
        yield h, mp3[i + 4:i + 4 + side], mp3[i + 4 + side:i + size]
        i += size


def granules(mp3):
    """MP3 with the bit reservoir off (main_data_begin 0) -> EA frames, one per granule."""
    out = []
    for h, side, main in mp3_frames(mp3):
        if b"Xing" in main[:40] or b"Info" in main[:40]:
            continue  # LAME's tag frame: no audio
        mono = (h >> 6 & 3) == 3
        nch = 1 if mono else 2
        b = Bits(side)
        assert b.read(9) == 0, "bit reservoir in use: encode with -reservoir 0"
        b.read(5 if mono else 3)
        scfsi = [b.read(4) for _ in range(nch)]
        info = [[(b.read(12), b.read(32), b.read(15)) for _ in range(nch)] for _ in range(2)]
        bit = 0
        for gr in range(2):
            w = Writer()
            for v in (h >> 19 & 3, h >> 10 & 3, h >> 6 & 3, h >> 4 & 3):
                w.write(v, 2)
            w.write(gr, 1)
            for s in scfsi if gr else ():
                w.write(s, 4)
            for size, o1, o2 in info[gr]:
                w.write(size, 12)
                w.write(o1, 32)
                w.write(o2, 15)
            for size, _, _ in info[gr]:
                w.copy(main, bit, size)
                bit += size
            common = w.bytes()
            assert 2 + len(common) < 4096
            out.append(struct.pack(">H", (0 if mono else 1) << 14 | 2 + len(common)) + common)
    return out


def parse(frame):
    """EA frame -> dict: header, granule index, scfsi, side info, main data bit offset."""
    b = Bits(frame)
    ext, _, _, size = b.read(1), b.read(1), b.read(2), b.read(12)
    pcm = 0
    if ext:
        b.read(2)
        b.read(10)
        pcm = b.read(10)
        b.read(10)
    hdr = [b.read(2) for _ in range(4)]
    nch = 1 if hdr[2] == 3 else 2
    gr = b.read(1)
    scfsi = [b.read(4) for _ in range(nch)] if gr else None
    info = [(b.read(12), b.read(32), b.read(15)) for _ in range(nch)]
    return {"size": size, "pcm": pcm, "hdr": hdr, "gr": gr, "scfsi": scfsi, "info": info, "data": b.p, "raw": frame}


def to_mp3(frames):
    """Parsed EA frames -> 320 kbps MP3 frames (main_data_begin 0), to check a stream decodes."""
    out = bytearray()
    for g0, g1 in zip(frames[0::2], frames[1::2]):
        assert g0["gr"] == 0 and g1["gr"] == 1
        v, sr, cm, me = g0["hdr"]
        w = Writer()
        for val, n in ((0x7FF, 11), (v, 2), (1, 2), (1, 1), (14, 4), (sr, 2), (0, 1), (0, 1), (cm, 2), (me, 2),
                       (0, 1), (1, 1), (0, 2), (0, 9), (0, 5 if cm == 3 else 3)):
            w.write(val, n)
        for s in g1["scfsi"]:
            w.write(s, 4)
        for g in (g0, g1):
            for size, o1, o2 in g["info"]:
                w.write(size, 12)
                w.write(o1, 32)
                w.write(o2, 15)
        for g in (g0, g1):
            bit = g["data"]
            for size, _, _ in g["info"]:
                w.copy(g["raw"], bit, size)
                bit += size
        f = w.bytes()
        target = 144000 * 320 // [44100, 48000, 32000][sr]
        if len(f) > target:
            raise ValueError(f"granule pair needs {len(f)} > {target} bytes at 320 kbps")
        out += f + bytes(target - len(f))
    return bytes(out)


def sps_frames(sps):
    """EAAC SPS stream -> ((h1, h2), [(block samples, [EA frame bytes])])."""
    p = int.from_bytes(sps[1:4], "big")
    h1, h2 = struct.unpack_from(">II", sps, 4)
    blocks = []
    while sps[p] == 0x44:
        size = int.from_bytes(sps[p + 1:p + 4], "big")
        q, frames = p + 8, []
        while q < p + size:
            fs = struct.unpack_from(">H", sps, q)[0] & 0xFFF
            frames.append(sps[q:q + fs])
            q += fs
        assert q == p + size
        blocks.append((struct.unpack_from(">I", sps, p + 4)[0], frames))
        p += size
    assert sps[p] == 0x45
    return (h1, h2), blocks


def sps(frames, rate=44100, channels=2, per_block=16):
    """EA frames -> EAAC SPS stream, codec 6, per_block granules per 'D' block like the bank."""
    n = 576 * len(frames)
    out = bytearray(b"\x48\x00\x00\x0c" + struct.pack(">II", 1 << 28 | 6 << 24 | (channels - 1) << 18 | rate,
                                                       1 << 30 | n))
    for i in range(0, len(frames), per_block):
        chunk = frames[i:i + per_block]
        body = b"".join(chunk)
        out += b"\x44" + (8 + len(body)).to_bytes(3, "big") + struct.pack(">I", 576 * len(chunk)) + body
    out += b"\x45\x00\x00\x04"
    return bytes(out + bytes(-len(out) % 0x20)), n


if __name__ == "__main__" and sys.argv[1:2] == ["check"]:
    (h1, h2), blocks = sps_frames(open(sys.argv[2], "rb").read())
    frames = [parse(f) for _, fs in blocks for f in fs]
    print("codec", h1 >> 24 & 15, "samples", h2 & 0x3FFFFFFF, "frames", len(frames),
          "pcm frames", sum(1 for f in frames if f["pcm"]),
          "block samples = 576 x frames:", all(n == 576 * len(fs) for n, fs in blocks))
    if len(sys.argv) > 3:
        open(sys.argv[3], "wb").write(to_mp3(frames))
