#!/usr/bin/env python3
"""Builds Basic/pc1600_i2c_installer-v1.0.txt from asm/i2c_z80_v1.0.asm.

The BASIC program POKEs the machine code (DATA lines in decimal) into the
machine-language area (reserve it first with NEW "S0:",&1000), then offers a
bus scanner (RUN 500) and a read/write test (RUN 700).
Check mode:  make_installer.py --check   (parses the DATA lines back and compares
them with the assembler output).
"""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from z80asm_mini import Assembler

ASM = os.path.join(here, '..', 'asm', 'i2c_z80_v1.0.asm')
OUT = os.path.join(here, '..', 'Basic', 'archive', 'pc1600_i2c_installer-v1.0.txt')
PER_LINE = 10

HEAD = [
    '10 REM I2C MASTER FOR THE PC-1600, Z80, V1.0',
    '20 REM BEFORE LOADING TYPE:  NEW "S0:",&1000',
    '30 READ N : IF N = 0 GOTO 70',
    '40 READ A : FOR I = 1 TO N : READ B : POKE A, B : A = A + 1 : NEXT I : GOTO 30',
    '70 PRINT "I2C Z80 V1.0 INSTALLED"',
    '80 PRINT "POKE &C5FC,D,W,R : CALL &C400,E"',
    '90 PRINT "RUN 500 = SCANNER, RUN 700 = TEST" : END',
    '500 REM SCANNER: DEVICES AT 8 TO 119',
    '510 POKE &C5FD, 0, 0',
    '520 FOR D = 8 TO 119',
    '530 POKE &C5FC, D : CALL &C400, E',
    '540 IF E = 0 THEN PRINT "FOUND &"; HEX$(D)',
    '550 NEXT D',
    '560 PRINT "SCAN DONE" : END',
    '700 REM TEST: WRITE W BYTES, THEN READ R BYTES',
    '710 INPUT "DEVICE ADDRESS (DEC)"; D',
    '720 INPUT "BYTES TO WRITE (0-8)"; W',
    '730 IF W = 0 GOTO 760',
    '740 FOR I = 0 TO W - 1 : INPUT "BYTE (DEC)"; B : POKE &C700 + I, B : NEXT I',
    '760 INPUT "BYTES TO READ (0-8)"; R',
    '770 POKE &C5FC, D, W, R : CALL &C400, E',
    '780 PRINT "RESULT "; E',
    '790 IF R = 0 OR E <> 0 THEN 820',
    '800 FOR I = 0 TO R - 1 : PRINT PEEK (&C600 + I); " "; : NEXT I',
    '810 PRINT',
    '820 END',
]


def data_lines(segs):
    lines = []
    n = 1000
    for addr, data in segs:
        for i in range(0, len(data), PER_LINE):
            chunk = data[i:i + PER_LINE]
            lines.append('%d DATA %d,%d,%s' % (n, len(chunk), addr + i, ','.join(str(b) for b in chunk)))
            n += 1
    lines.append('%d DATA 0' % n)
    return lines


def build():
    a = Assembler()
    a.assemble(open(ASM).read())
    return a, HEAD + data_lines(a.segments())


def parse_back(text):
    mem = {}
    nums = []
    for ln in text.splitlines():
        m = re.match(r'^\d+ DATA (.*)$', ln)
        if m:
            nums += [int(x) for x in m.group(1).split(',')]
    i = 0
    while nums[i] != 0:
        n, addr = nums[i], nums[i + 1]
        for k in range(n):
            mem[addr + k] = nums[i + 2 + k]
        i += 2 + n
    return mem


if __name__ == '__main__':
    a, lines = build()
    text = '\n'.join(lines) + '\n'
    if '--check' in sys.argv:
        ok = parse_back(open(OUT).read()) == a.image
        longest = max(len(l) for l in open(OUT).read().splitlines())
        print('DATA lines reproduce the assembler image:', ok, '| longest line', longest, 'characters')
        sys.exit(0 if ok and longest <= 79 else 1)
    open(OUT, 'w').write(text)
    print('written', OUT, len(lines), 'lines')
