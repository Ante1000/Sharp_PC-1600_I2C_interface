#!/usr/bin/env python3
"""Builds Basic/pc1600_i2c_lh_diag-v1.0.txt (BASIC program + the LH diagnostic code in DATA lines)
from asm/i2c_lh_diag_v1.0.asm. --check compares the DATA lines with the assembler output."""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from lh5801asm_mini import Asm

ASM = os.path.join(here, '..', 'asm', 'i2c_lh_diag_v1.0.asm')
OUT = os.path.join(here, '..', 'Basic', 'pc1600_i2c_lh_diag-v1.0.txt')
Z80_BASE = 0x8000 + 0x4D00

PROG = [
    '10 REM *** PC-1600 I2C LH DIAGNOSTIC: SDA=PIN 15+27 SCL=PIN 29 ***',
    '20 REM FIRST: NEW "S0:",&1000. DIODE ON PIN 15 ONLY, PIN 31 DISCONNECTED',
    '30 H = PEEK (63589) : H = H + 128 - 256 * INT (H / 128)',
    '32 S = H * 256 + PEEK (63590)',
    '34 IF S < 53248 THEN PRINT "NEW S0:,&1000 FIRST" : END',
    '40 WAIT 64 : PRINT "Installing..." : RESTORE 2000',
    '50 READ N : IF N = 0 THEN 80',
    '60 READ A : FOR I = 1 TO N : READ B : POKE A, B : A = A + 1 : NEXT I',
    '70 GOTO 50',
    '80 PRINT "Testing..." : E = 0 : XCALL &4D00, E',
    '90 T = &CDF0 : F = 0 : WAIT 128',
    '100 IF PEEK (T) = 1 THEN LET F = F + 1 : PRINT "E1 DDB BIT 2 STAYS SET"',
    '110 IF PEEK (T + 1) = 0 THEN LET F = F + 1 : PRINT "E2 RPU: SDA NOT PULLED LOW"',
    '120 IF PEEK (T + 3) = 0 THEN LET F = F + 1 : PRINT "E3 SDA STAYS LOW AFTER SPU"',
    '125 B = PEEK (T + 3)',
    '130 IF B = 1 AND PEEK (T + 5) = 0 THEN LET F = F + 1 : PRINT "E4 SDA TOO SLOW"',
    '140 IF PEEK (T + 6) = 0 THEN LET F = F + 1 : PRINT "E5 SDA LOW AFTER 10 CLK"',
    '150 IF PEEK (T + 7) = 0 THEN LET F = F + 1 : PRINT "E6 START: SDA NOT LOW"',
    '160 IF PEEK (T + 8) = 0 THEN LET F = F + 1 : PRINT "E7 STOP: SDA NOT HIGH"',
    '170 Q = (255 - PEEK (T + 4)) * 25 : PRINT "SDA RISE ABOUT "; Q; " US"',
    '180 IF F = 0 THEN PRINT "ALL OK"',
    '190 WAIT 0 : END',
]


def build():
    a = Asm({})
    code = a.assemble(open(ASM).read())
    lines = list(PROG)
    n = 2000
    for i in range(0, len(code), 10):
        c = code[i:i + 10]
        lines.append('%d DATA %d,%d,%s' % (n, len(c), Z80_BASE + i, ','.join(str(b) for b in c)))
        n += 1
    lines.append('%d DATA 0' % n)
    return code, '\n'.join(lines) + '\n'


def parse_back(text):
    nums = []
    for ln in text.splitlines():
        m = re.match(r'^\d+ DATA (.*)$', ln)
        if m:
            nums += [int(x) for x in m.group(1).split(',')]
    mem, i = {}, 0
    while nums[i] != 0:
        n, addr = nums[i], nums[i + 1]
        for k in range(n):
            mem[addr + k] = nums[i + 2 + k]
        i += 2 + n
    return mem


if __name__ == '__main__':
    code, text = build()
    if '--check' in sys.argv:
        t = open(OUT).read()
        ok = parse_back(t) == {Z80_BASE + i: b for i, b in enumerate(code)} and t == text
        longest = max(len(l) for l in t.splitlines())
        print('diag: DATA = assembler image, file up to date: %s | %d bytes | longest line %d' % (ok, len(code), longest))
        sys.exit(0 if ok and longest <= 80 else 1)
    open(OUT, 'w').write(text)
    print('written', OUT, len(code), 'bytes')
