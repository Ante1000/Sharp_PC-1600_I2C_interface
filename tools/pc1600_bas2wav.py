#!/usr/bin/env python3
"""pc1600_bas2wav.py - BASIC text file -> tape recording (WAV) for the Sharp PC-1600 in MODE 1.

Usage:  python3 pc1600_bas2wav.py program.txt out.wav [TAPENAME]
        python3 pc1600_bas2wav.py --check in.wav [program.txt]   (decode a recording; compare with a text)

The program is tokenized with the token table of the PC-1600 (the tokenizer of SerComet,
https://github.com/Ante1000/SerComet_transfer_tool_for_pockets, ported to Python) and written in
the tape format of the PC-1500 / CE-150 (44100 Hz, 8 bit mono), so it can be loaded with CLOAD
after switching the PC-1600 to MODE 1; then switch back to MODE 0 and RUN it. The tape format
functions are those of pc1500_bas2wav.py of the PC-1500 I2C repository.

Tape format: bit 1 = 8 cycles of 2500 Hz, bit 0 = 4 cycles of 1250 Hz, 141 samples per bit;
leader 8 s of 2500 Hz; frame = one nibble (0, d0..d3, 1 1 1 1 1 1); header block of 42 bytes
with the name (at most 7 characters), the program in chunks of 80 bytes with 16-bit sums.
Check: tools/pc1600_bas2wav.py reproduces the recording wav/sl1600_mode1_CE-150.wav of the
SerComet repository byte for byte (see README).
"""
import re
import sys
import wave

FS = 44100
BIT = 141.12   # samples per bit (8 cycles of 2500 Hz)

T1600 = {
    "PAPER": 0xE381, "CSIZE": 0xE680, "GRAPH": 0xE681, "GLCURSOR": 0xE682,
    "SORGN": 0xE684, "ROTATE": 0xE685, "TEXT": 0xE686, "RMT": 0xE7A9,
    "DEV$": 0xE857, "COM$": 0xE858, "INSTAT": 0xE859, "RINKEY$": 0xE85A,
    "OUTSTAT": 0xE880, "SETCOM": 0xE882, "TERMINAL": 0xE883, "DTE": 0xE884,
    "TRANSMIT": 0xE885, "SETDEV": 0xE886, "ERN": 0xF052, "ERL": 0xF053,
    "SPACE$": 0xF061, "CURSOR": 0xF084, "USING": 0xF085, "WDTH": 0xF087,
    "CLS": 0xF088, "CLOAD": 0xF089, "MERGE": 0xF08F, "LIST": 0xF090,
    "INPUT": 0xF091, "GCURSOR": 0xF093, "CSAVE": 0xF095, "PRINT": 0xF097,
    "FILES": 0xF098, "LINE": 0xF099, "PRESET": 0xF09A, "PSET": 0xF09B,
    "GPRINT": 0xF09F, "LFILES": 0xF0A0, "PITCH": 0xF0A4, "LCURSOR": 0xF0A5,
    "FEED": 0xF0B0, "CONSOLE": 0xF0B1, "CHAIN": 0xF0B2, "BREAK": 0xF0B3,
    "ZONE": 0xF0B4, "COLOR": 0xF0B5, "LF": 0xF0B6, "LLINE": 0xF0B7,
    "LLIST": 0xF0B8, "LPRINT": 0xF0B9, "RLINE": 0xF0BA, "TAB": 0xF0BB,
    "TEST": 0xF0BC, "AND": 0xF150, "OR": 0xF151, "MEM": 0xF158,
    "TIME": 0xF15B, "INKEY$": 0xF15C, "PI": 0xF15D, "ASC": 0xF160,
    "STR$": 0xF161, "VAL": 0xF162, "CHR$": 0xF163, "LEN": 0xF164,
    "DEG": 0xF165, "DMS": 0xF166, "STATUS": 0xF167, "POINT": 0xF168,
    "SQR": 0xF16B, "NOT": 0xF16D, "XPEEK#": 0xF16E, "XPEEK": 0xF16F,
    "ABS": 0xF170, "INT": 0xF171, "RIGHT$": 0xF172, "ASN": 0xF173,
    "ACS": 0xF174, "ATN": 0xF175, "LN": 0xF176, "LOG": 0xF177,
    "EXP": 0xF178, "SGN": 0xF179, "LEFT$": 0xF17A, "MID$": 0xF17B,
    "RND": 0xF17C, "SIN": 0xF17D, "COS": 0xF17E, "TAN": 0xF17F,
    "AREAD": 0xF180, "ARUN": 0xF181, "BEEP": 0xF182, "CONT": 0xF183,
    "GRAD": 0xF186, "CLEAR": 0xF187, "XCALL": 0xF18A, "DIM": 0xF18B,
    "DEGREE": 0xF18C, "DATA": 0xF18D, "END": 0xF18E, "GOTO": 0xF192,
    "GOSUB": 0xF194, "IF": 0xF196, "LET": 0xF198, "RETURN": 0xF199,
    "NEXT": 0xF19A, "NEW": 0xF19B, "ON": 0xF19C, "OPN": 0xF19D,
    "OFF": 0xF19E, "XPOKE#": 0xF1A0, "XPOKE": 0xF1A1, "PAUSE": 0xF1A2,
    "RUN": 0xF1A4, "FOR": 0xF1A5, "READ": 0xF1A6, "RESTORE": 0xF1A7,
    "RANDOM": 0xF1A8, "RADIAN": 0xF1AA, "REM": 0xF1AB, "STOP": 0xF1AC,
    "STEP": 0xF1AD, "THEN": 0xF1AE, "TRON": 0xF1AF, "TROFF": 0xF1B0,
    "TO": 0xF1B1, "WAIT": 0xF1B3, "ERROR": 0xF1B4, "LOCK": 0xF1B5,
    "UNLOCK": 0xF1B6, "EOF": 0xF271, "LOC": 0xF272, "LOF": 0xF273,
    "DSKF": 0xF274, "MOD": 0xF250, "XOR": 0xF251, "RXD$": 0xF256,
    "DATE$": 0xF257, "TIME$": 0xF258, "AIN": 0xF25A, "ALARM$": 0xF25C,
    "WAKE$": 0xF261, "ACNV$": 0xF262, "HEX$": 0xF265, "INP": 0xF266,
    "INSTR": 0xF267, "PEEK": 0xF26D, "PEEK#": 0xF26E, "ADIN": 0xF280,
    "CALL": 0xF282, "ELSE": 0xF283, "KBUFF$": 0xF284, "KEY": 0xF285,
    "KEYSTAT": 0xF286, "KILL": 0xF287, "MAXFILES": 0xF288, "OUT": 0xF28A,
    "POWER": 0xF28B, "POKE": 0xF28C, "RESUME": 0xF28D, "RETI": 0xF28E,
    "BLOAD": 0xF290, "BSAVE": 0xF291, "CLOSE": 0xF292, "COPY": 0xF293,
    "INIT": 0xF294, "LOAD": 0xF295, "OPEN": 0xF296, "NAME": 0xF297,
    "SET": 0xF298, "SAVE": 0xF299, "PHONE": 0xF2A0, "SNDBRK": 0xF2A1,
    "SNDSTAT": 0xF2A2, "COM": 0xF2A3, "RCVSTAT": 0xF2A4, "PCONSOLE": 0xF2B1,
    "MODE": 0xF2B3, "PZONE": 0xF2B4, "RENUM": 0xF2B5, "AUTO": 0xF2B6,
    "ERASE": 0xF2B7, "PASS": 0xF2B8, "DELETE": 0xF2B9, "TITLE": 0xF2BA,
    "AOFF": 0xF2BC, "AS": 0xF2BD, "OUTPUT": 0xF2BE, "APPEND": 0xF2BF
}
# longest keyword first, then ordinal order (as SerComet does)
BY_LENGTH = sorted(T1600.items(), key=lambda kv: (-len(kv[0]), kv[0]))
LINE_KEYWORDS = {"GOTO", "GOSUB", "THEN", "ELSE", "RESTORE", "RUN", "RESUME", "LIST", "LLIST",
                 "DELETE", "RENUM", "AUTO"}


def tokenize_body(s):
    """Port of Pc1600Basic.TokenizeBody (binary line numbers after GOTO, THEN, ...)."""
    o = bytearray()
    i = 0
    n = len(s)
    line_mode = False
    while i < n:
        c = s[i]
        if c in ' \t':
            i += 1
            continue
        if c == '"':
            o.append(0x22)
            i += 1
            while i < n:
                q = s[i]
                i += 1
                o.append(ord(q))
                if q == '"':
                    break
            line_mode = False
            continue
        if line_mode and c.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            v = int(s[i:j])
            if v > 65535:
                raise ValueError('bad line number %d' % v)
            o += bytes([0x1F, v >> 8, v & 255, 0x00])
            i = j
            k = i
            while k < n and s[k] == ' ':
                k += 1
            if k < n and s[k] == ',':
                o.append(ord(','))
                i = k + 1
            else:
                line_mode = False
            continue
        kw = None
        for name, code in BY_LENGTH:
            if s[i:i + len(name)].upper() == name:
                kw = name
                break
        if kw is not None:
            code = T1600[kw]
            o += bytes([code >> 8, code & 255])
            i += len(kw)
            if kw in ("REM", "DATA"):
                if i < n and s[i] == ' ':
                    i += 1
                in_q = False
                while i < n:
                    if s[i] == '"':
                        in_q = not in_q
                    if kw == "DATA" and not in_q and s[i] == ' ':
                        i += 1
                        continue
                    o.append(ord(s[i]))
                    i += 1
                return bytes(o)
            line_mode = kw in LINE_KEYWORDS
            continue
        line_mode = False
        o.append(ord(c.upper()) if 'a' <= c <= 'z' else ord(c))
        i += 1
    return bytes(o)


def tokenize(text):
    """BASIC text -> program image (lines only, like the .img of SerComet) + FF end marker."""
    lines = {}
    for raw in text.split('\n'):
        s = raw.rstrip('\r \t\x1a')
        if not s.strip():
            continue
        m = re.match(r' *(\d+)(.*)$', s)
        if not m:
            raise ValueError('no line number: ' + s)
        no = int(m.group(1))
        if not 1 <= no <= 65279:
            raise ValueError('line number out of range: %d' % no)
        body = tokenize_body(m.group(2)) + b'\x0d'
        if len(body) > 255:
            raise ValueError('line %d too long (%d bytes)' % (no, len(body)))
        lines[no] = bytes([no >> 8, no & 255, len(body)]) + body
    return b''.join(lines[k] for k in sorted(lines)) + b'\xff'


def header(name, prog):
    nm = name.upper().encode('latin1')[:7]
    h = bytes([0x10,0x11,0x12,0x13,0x14,0x15,0x16,0x17,0x01]) + nm + bytes(26 - len(nm))
    n = len(prog) - 1
    h += bytes([0xC5, n >> 8, n & 255, 0, 0])
    s = sum(h)
    return h + bytes([s >> 8, s & 255])

def chunks(prog):
    out = bytearray()
    for p in range(0, len(prog), 80):
        c = prog[p:p+80]; s = sum(c)
        out += c + bytes([s >> 8, s & 255])
    return bytes(out)

def nibbles(bs):
    r = []
    for b in bs: r += [b & 15, b >> 4]
    return r

def bitstream(name, prog):
    bits = []
    def frames(nibs):
        for x in nibs: bits.extend([0] + [(x >> k) & 1 for k in range(4)] + [1]*6)
    frames([0xA] + nibbles(header(name, prog)))
    bits.extend([1]*76)
    frames(nibbles(chunks(prog)))
    bits.extend([1]*73)
    frames([5, 5])
    bits.extend([1]*71)
    return bits

def synth(bits, leader_s=8.0):
    # list of (half-cycle length in samples, level)
    edges = []
    t = 0.0
    def tone(f, cycles):
        nonlocal t
        half = FS / f / 2
        for _ in range(cycles):
            t += half; edges.append((t, 1))
            t += half; edges.append((t, 0))
    tone(2500, int(round(leader_s * 2500)))
    for b in bits:
        if b: tone(2500, 8)
        else: tone(1250, 4)
    total = int(t) + 1
    buf = bytearray([128]) * total
    lo, hi = 30, 226
    prev = 0.0
    k = 0
    # first half of each cycle is high: edges alternate (end of high, end of low)
    start = 0.0
    level_hi = True
    pos = 0.0
    for e, _ in edges:
        a, b = int(round(pos)), int(round(e))
        v = hi if level_hi else lo
        for i in range(a, min(b, total)): buf[i] = v
        pos = e; level_hi = not level_hi
    return bytes(buf)

def write_wav(path, data):
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(1); w.setframerate(FS)
    w.writeframes(data); w.close()

def decode_wav(path):
    """returns (header bytes, program bytes with chunk sums verified)"""
    w = wave.open(path); d = w.readframes(w.getnframes())
    cr = []; prev = d[0] >= 128
    for i, v in enumerate(d):
        s = v >= 128
        if s and not prev: cr.append(i)
        prev = s
    runs = []
    for p in [b - a for a, b in zip(cr, cr[1:])]:
        c = 'S' if p >= 30 else ('F' if p < 22 else 'T')
        if c == 'T': continue
        if runs and runs[-1][0] == c: runs[-1][1] += p
        else: runs.append([c, p])
    r = []
    for c, t in runs:
        r += [0 if c == 'S' else 1] * round((t + (35 if c == 'S' else 17.6)) / 140.0)
    i = 0
    while i < len(r) and r[i] == 1: i += 1
    segs = []; cur = []
    while i + 11 <= len(r):
        f = r[i:i+11]
        if f[0] == 0 and f[5:] == [1]*6:
            cur.append(sum(x << k for k, x in enumerate(f[1:5]))); i += 11
        else:
            if cur: segs.append(cur); cur = []
            i += 1
    if cur: segs.append(cur)
    hdr = bytes((segs[0][k+1] << 4) | segs[0][k] for k in range(1, len(segs[0]) - 1, 2))
    raw = bytes((segs[1][k+1] << 4) | segs[1][k] for k in range(0, len(segs[1]) - 1, 2))
    prog = bytearray(); p = 0
    while p < len(raw):
        end = min(p + 80, len(raw) - 2); c = raw[p:end]
        if sum(c) & 0xffff != raw[end] * 256 + raw[end+1]: raise ValueError('chunk sum error at %d' % p)
        prog += c; p = end + 2
    return hdr, bytes(prog)


def main(a):
    if len(a) >= 2 and a[0] == '--check':
        h, p = decode_wav(a[1])
        print('name:', h[9:35].rstrip(b'\0').decode('latin1'), 'program bytes:', len(p) - 1)
        if len(a) == 3:
            want = tokenize(open(a[2], encoding='latin1').read())
            print('equal to the tokenized text:', p == want)
            return 0 if p == want else 1
        return 0
    if len(a) in (2, 3):
        prog = tokenize(open(a[0], encoding='latin1').read())
        name = a[2] if len(a) == 3 else re.sub(r'[^A-Za-z0-9]', '', a[0].split('/')[-1].split('.')[0])[:7]
        write_wav(a[1], synth(bitstream(name, prog)))
        print('%s: %d program bytes, tape name %s' % (a[1], len(prog) - 1, name.upper()[:7]))
        return 0
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
