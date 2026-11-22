#!/usr/bin/env python3
"""Builds the BASIC files of the Z80 driver v1.1 (= speed lab version V10):
  Basic/pc1600_i2c_installer-v1.1.txt         driver installer + scanner + test
  Basic/pc1600_bmp280-v1.1.txt                BMP280 program (needs the driver v1.1)
  Basic/archive/pc1600_i2c_z80_bmp280-v1.1.txt  installer and BMP280 program in one file (archived)
--check compares the DATA lines with the assembler output (asm/i2c_z80_v1.1.asm)."""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import make_installer as MI
import make_combined as MC
from z80asm_mini import Assembler

ASM = os.path.join(here, '..', 'asm', 'i2c_z80_v1.1.asm')
B = os.path.join(here, '..', 'Basic')
BA = os.path.join(B, 'archive')
RES = '&800'                     # C0C5-C7FF is enough for v1.1


def asm():
    a = Assembler()
    a.assemble(open(ASM).read())
    return a


def installer():
    a = asm()
    head = [l.replace('V1.0', 'V1.1').replace('&1000', RES) for l in MI.HEAD]
    return a, '\n'.join(head + MI.data_lines(a.segments())) + '\n'


METER = [
    '1000 REM --- I2C SPEED: REP DOES 10 READS PER CALL, EMPTY CALL SUBTRACTED ---',
    '1010 WAIT 64 : PRINT "Measuring I2C speed (25 s)..." : WAIT 0',
    '1020 POKE TX, &88 : POKE IA, D, 1, 255 : POKE 50682, 10',
    '1030 A = 50528 : G = 8 : GOSUB 1200 : OV = (H + .5) / N',
    '1040 A = 50560 : G = 16 : GOSUB 1200 : IF E <> 0 THEN 990',
    '1050 T = (H + .5) / N - OV : MS = INT (T * 100 + .5)',
    '1060 REM 2322 SCL CLOCKS PER READ: ADDR+REG 18, ADDR 9, 255 BYTES * 9',
    '1090 FQ = INT (23220 / T / 1000 + .5)',
    '1095 PRINT "255 B READ = "; MS; " ms" : RETURN',
]
CALLS = [
    '1200 REM --- CALL THE ROUTINE AT A FOR G SECONDS: N CALLS, H SECONDS ---',
    '1210 E = 0 : GOSUB 1100 : Y = X',
    '1220 GOSUB 1100 : IF X = Y THEN 1220',
    '1230 W = X : N = 0',
    '1240 CALL A, E : N = N + 1 : IF E <> 0 THEN RETURN',
    '1250 GOSUB 1100 : H = X - W : IF H < 0 THEN LET H = H + 3600',
    '1260 IF H < G THEN 1240',
    '1270 RETURN',
]


def bmp280():
    t = open(os.path.join(BA, 'pc1600_bmp280-v1.0.txt')).read()
    t = t.replace('NEEDS Z80 I2C V1.0 AT &C400', 'NEEDS Z80 I2C V1.1 AT &C400')
    lines = [l for l in t.splitlines() if not re.match(r'^(1000|10[1-9]\d) ', l)]
    i = next(k for k, l in enumerate(lines) if l.startswith('1100 '))
    return '\n'.join(lines[:i] + METER + lines[i:] + CALLS) + '\n'


def combined():
    a = asm()
    src = bmp280().splitlines()
    head = ['3 REM I2C Z80 DRIVER V1.1 + BMP280', '4 REM FIRST TYPE:  NEW0  THEN  NEW "S0:",&800',
            '5 IF PEEK (&C141) <> 123 THEN GOSUB 3000']
    return a, '\n'.join(head + src + MC.SUB + MC.data_lines(a.segments())) + '\n'


def targets():
    ai, ti = installer()
    ac, tc = combined()
    return [('pc1600_i2c_installer-v1.1.txt', ti, ai.image),
            ('pc1600_bmp280-v1.1.txt', bmp280(), None),
            ('pc1600_i2c_z80_bmp280-v1.1.txt', tc, ac.image)]


if __name__ == '__main__':
    bad = 0
    for fn, text, img in targets():
        path = os.path.join(BA if 'z80_bmp280' in fn else B, fn)
        if '--check' in sys.argv:
            t = open(path).read()
            ok = t == text and (img is None or MC.parse_back(t) == img)
            longest = max(len(l) for l in t.splitlines())
            nums = [int(m.group(1)) for m in re.finditer(r'^(\d+) ', t, re.M)]
            print('%s: up to date and DATA = assembler image: %s | longest %d | ascending %s'
                  % (fn, ok, longest, nums == sorted(set(nums))))
            bad += 0 if ok and longest <= 80 and nums == sorted(set(nums)) else 1
        else:
            open(path, 'w').write(text)
            print('written', fn, len(text.splitlines()), 'lines')
    sys.exit(1 if bad else 0)
