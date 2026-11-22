#!/usr/bin/env python3
"""Builds Basic/pc1600_i2c_lh_installer-v1.0.txt from asm/i2c_lh_v1.0.asm (LH-5803 driver).
The code is POKEd (Z80 addresses = LH addresses + &8000) into &CC00 and up.
Check mode: make_installer_lh.py --check"""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from lh5801asm_mini import Asm

ASM = os.path.join(here, '..', 'asm', 'i2c_lh_v1.0.asm')
OUT = os.path.join(here, '..', 'Basic', 'pc1600_i2c_lh_installer-v1.0.txt')
CONSTS = {'IP': 0x4C, 'TP': 0x4B, 'RP': 0x4A, 'BM': 4, 'DB': 0xFB}
Z80_BASE = 0x8000 + 0x4C00     # Z80 address of the first byte of the code
PER_LINE = 10

HEAD = [
    '10 REM I2C MASTER LH (XCALL) FOR THE PC-1600, V1.0',
    '20 REM BEFORE LOADING TYPE:  NEW "S0:",&1000',
    '30 READ N : IF N = 0 THEN 70',
    '40 READ A : FOR I = 1 TO N : READ B : POKE A, B : A = A + 1 : NEXT I : GOTO 30',
    '70 PRINT "I2C LH V1.0 INSTALLED"',
    '80 PRINT "POKE &CCFC,D,W,R : XCALL &4C00,E"',
    '90 PRINT "RUN 500 = SCANNER, RUN 700 = TEST" : END',
    '500 REM SCANNER: DEVICES AT 8 TO 119',
    '510 POKE &CCFD, 0, 0',
    '520 FOR D = 8 TO 119',
    '530 POKE &CCFC, D : XCALL &4C00, E',
    '540 IF E = 0 THEN PRINT "FOUND &"; HEX$(D)',
    '550 NEXT D',
    '560 PRINT "SCAN DONE" : END',
    '700 REM TEST: WRITE W BYTES, THEN READ R BYTES',
    '710 INPUT "DEVICE ADDRESS (DEC)"; D',
    '720 INPUT "BYTES TO WRITE (0-8)"; W',
    '730 IF W = 0 THEN 760',
    '740 FOR I = 0 TO W - 1 : INPUT "BYTE (DEC)"; B : POKE &CB00 + I, B : NEXT I',
    '760 INPUT "BYTES TO READ (0-8)"; R',
    '770 POKE &CCFC, D, W, R : XCALL &4C00, E',
    '780 PRINT "RESULT "; E',
    '790 IF R = 0 OR E <> 0 THEN 820',
    '800 FOR I = 0 TO R - 1 : PRINT PEEK (&CA00 + I); " "; : NEXT I',
    '810 PRINT',
    '820 END',
]


def build():
    a = Asm(CONSTS)
    code = a.assemble(open(ASM).read())
    lines = list(HEAD)
    n = 1000
    for i in range(0, len(code), PER_LINE):
        chunk = code[i:i + PER_LINE]
        lines.append('%d DATA %d,%d,%s' % (n, len(chunk), Z80_BASE + i, ','.join(str(b) for b in chunk)))
        n += 1
    lines.append('%d DATA 0' % n)
    return code, lines


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
    code, lines = build()
    if '--check' in sys.argv:
        mem = parse_back(open(OUT).read())
        ok = mem == {Z80_BASE + i: b for i, b in enumerate(code)}
        longest = max(len(l) for l in open(OUT).read().splitlines())
        print('DATA lines reproduce the assembler image:', ok, '| %d bytes | longest line %d' % (len(code), longest))
        sys.exit(0 if ok and longest <= 80 else 1)
    open(OUT, 'w').write('\n'.join(lines) + '\n')
    print('written', OUT, len(code), 'bytes')
