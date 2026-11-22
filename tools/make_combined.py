#!/usr/bin/env python3
"""Builds the combined programs (driver installer + BMP280 program in one BASIC file):
  Basic/pc1600_i2c_z80_bmp280-v1.0.txt   (Z80 driver)
  Basic/pc1600_i2c_lh_bmp280-v1.0.txt    (LH-5803 driver)
The machine code is in DATA lines (4000 and up); a subroutine (line 3000) POKEs it when the
driver is not in memory. Check mode (--check) reads the DATA lines back and compares them
with the assembler output."""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from z80asm_mini import Assembler
from lh5801asm_mini import Asm
import make_installer_lh as LH

B = os.path.join(here, '..', 'Basic', 'archive')
Z80_ASM = os.path.join(here, '..', 'asm', 'i2c_z80_v1.0.asm')

SUB = [
    '3000 REM --- INSTALL THE I2C CODE FROM THE DATA LINES ---',
    '3010 H = PEEK (63589) : H = H + 128 - 256 * INT (H / 128)',
    '3012 S = H * 256 + PEEK (63590)',
    '3020 PRINT "PROGRAM AT "; S; " (&D000 = 53248)"',
    '3022 INPUT "DID YOU TYPE NEW S0 (Y)"; A$ : IF A$ <> "Y" THEN END',
    '3030 WAIT 64 : PRINT "Installing I2C..." : WAIT 0 : RESTORE 4000',
    '3040 READ N : IF N = 0 THEN RETURN',
    '3050 READ A : FOR I = 1 TO N : READ B : POKE A, B : A = A + 1 : NEXT I',
    '3060 GOTO 3040',
]


def data_lines(segs, per=10):
    out, n = [], 4000
    for addr, data in segs:
        for i in range(0, len(data), per):
            c = data[i:i + per]
            out.append('%d DATA %d,%d,%s' % (n, len(c), addr + i, ','.join(str(x) for x in c)))
            n += 1
    out.append('%d DATA 0' % n)
    return out


def z80_image():
    a = Assembler()
    a.assemble(open(Z80_ASM).read())
    return a.segments(), dict(a.image)


def lh_image():
    a = Asm(LH.CONSTS)
    code = a.assemble(open(LH.ASM).read())
    return [(LH.Z80_BASE, list(code))], {LH.Z80_BASE + i: b for i, b in enumerate(code)}


def build(name, bmp_file, segs, check_expr, title):
    src = open(os.path.join(B, bmp_file)).read().splitlines()
    head = ['3 REM ' + title, '4 REM FIRST TYPE:  NEW "S0:",&1000', '5 IF %s THEN GOSUB 3000' % check_expr]
    return '\n'.join(head + src + SUB + data_lines(segs)) + '\n'


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


def targets():
    zs, zi = z80_image()
    ls, li = lh_image()
    return [
        ('pc1600_i2c_z80_bmp280-v1.0.txt', build('z80', 'pc1600_bmp280-v1.0.txt', zs,
                                                'PEEK (&C400) <> 62', 'I2C Z80 DRIVER + BMP280 (V1.0)'), zi),
        ('pc1600_i2c_lh_bmp280-v1.0.txt', build('lh', 'pc1600_bmp280_lh-v1.0.txt', ls,
                                               'PEEK (&CC00) <> 253', 'I2C LH-5803 DRIVER + BMP280 (V1.0)'), li),
    ]


if __name__ == '__main__':
    bad = 0
    for fn, text, img in targets():
        path = os.path.join(B, fn)
        if '--check' in sys.argv:
            t = open(path).read()
            ok = parse_back(t) == img and t == text
            longest = max(len(l) for l in t.splitlines())
            nums = [int(m.group(1)) for m in re.finditer(r'^(\d+) ', t, re.M)]
            print('%s: DATA = assembler image and file up to date: %s | longest line %d | lines ascending: %s'
                  % (fn, ok, longest, nums == sorted(set(nums))))
            bad += 0 if ok and longest <= 80 and nums == sorted(set(nums)) else 1
        else:
            open(path, 'w').write(text)
            print('written', fn, len(text.splitlines()), 'lines')
    sys.exit(1 if bad else 0)
