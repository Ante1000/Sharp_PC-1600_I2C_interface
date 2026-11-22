#!/usr/bin/env python3
"""Builds Basic/pc1600_z80_portlab-v1.0.txt: times the Z80 I/O instructions on the real PC-1600.

The routines (each 256 * 10 * 100 = 256000 accesses) are POKEd to C100... and timed by BASIC like the
speed lab (30 s windows are not needed: one call lasts 0.4 to 2 s). Result: microseconds per access
(a NOP routine gives the clock, the others the cost of OUT / IN and the influence of the port and of the
high address byte B). --check compares the DATA lines with the assembler and runs every routine in the
simulator (count and termination)."""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from z80asm_mini import Assembler

ROOT = os.path.join(here, '..')
OUTF = os.path.join(ROOT, 'Basic', 'pc1600_z80_portlab-v1.0.txt')
BASE, STEP = 0xC100, 0x30
OUTER = 100

# name (6 characters at most), setup lines, access instruction (10 per inner loop pass)
ROUTINES = [
    ('NOP', '', 'NOP'),
    ('OUT n', 'LD A,01h', 'OUT (18h),A'),
    ('OUT C', 'LD BC,0118h\n        LD H,01h', 'OUT (C),H'),
    ('IN A,n', 'LD A,6Bh', 'IN A,(1Fh)'),
    ('1F B=01', 'LD BC,011Fh', 'IN H,(C)'),
    ('1F B=00', 'LD BC,001Fh', 'IN H,(C)'),
    ('1F B=81', 'LD BC,811Fh', 'IN H,(C)'),
    ('1E B=01', 'LD BC,011Eh', 'IN H,(C)'),
    ('1D B=01', 'LD BC,011Dh', 'IN H,(C)'),
    ('1C B=01', 'LD BC,011Ch', 'IN H,(C)'),
    ('1B B=01', 'LD BC,011Bh', 'IN H,(C)'),
    ('1A B=01', 'LD BC,011Ah', 'IN H,(C)'),
    ('19 B=01', 'LD BC,0119h', 'IN H,(C)'),
    ('18 B=01', 'LD BC,0118h', 'IN H,(C)'),
]
BR = 0xC0D0          # empty routine (RET) inside the reserved area


def source():
    out = ['        ORG 0%04Xh\n        RET\n' % BR]
    for k, (name, setup, ins) in enumerate(ROUTINES):
        s = '        ORG 0%04Xh\nR%d:     DI\n' % (BASE + k * STEP, k)
        if setup:
            s += '        %s\n' % setup
        s += '        LD D,%d\nO%d:     LD E,0\nI%d:\n' % (OUTER, k, k)
        s += ('        %s\n' % ins) * 10
        s += '        DEC E\n        JR NZ,I%d\n        DEC D\n        JR NZ,O%d\n        EI\n        RET\n' % (k, k)
        out.append(s)
    return ''.join(out)


PROG = [
    '10 REM *** PC-1600 PORT LAB: TIME OF IN / OUT / NOP IN MICROSECONDS ***',
    '20 REM FIRST: NEW0 THEN NEW "S0:",&800. NO HARDWARE NEEDED',
    '30 CLEAR : WAIT 0',
    '40 PRINT "Installing..."',
    '50 READ N : IF N = 0 THEN 80',
    '60 READ A : FOR I = 1 TO N : READ B : POKE A, B : A = A + 1 : NEXT I',
    '70 GOTO 50',
    '80 WAIT 64 : PRINT "BASIC CALL (20 S)" : WAIT 0',
    '90 A = %d : G = 20 : GOSUB 900 : OV = (H + .5) / N' % BR,
    '100 WAIT 128 : PRINT "CALL "; INT (OV * 10000 + .5) / 10; " ms"',
    '110 FOR J = 0 TO %d : READ T$ : A = %d + J * %d : G = 12 : GOSUB 900' % (len(ROUTINES) - 1, BASE, STEP),
    '120 U = ((H + .5) / N - OV) * 1000000 / %d' % (256 * 10 * OUTER),
    '130 PRINT T$; " "; INT (U * 1000 + .5) / 1000; " us" : NEXT J',
    '140 WAIT 0 : END',
    '900 REM --- CALL THE ROUTINE AT A FOR G SECONDS: N CALLS, H SECONDS ---',
    '910 E = 0 : GOSUB 1000 : Y = X',
    '920 GOSUB 1000 : IF X = Y THEN 920',
    '930 W = X : N = 0',
    '940 CALL A, E : N = N + 1',
    '950 GOSUB 1000 : H = X - W : IF H < 0 THEN LET H = H + 3600',
    '960 IF H < G THEN 940',
    '970 RETURN',
    '1000 REM --- SECONDS OF THE HOUR FROM TIME (MMDDHH.mmss) INTO X ---',
    '1010 Q = INT ((TIME - INT (TIME)) * 10000 + .5)',
    '1020 X = INT (Q / 100) * 60 + Q - 100 * INT (Q / 100) : RETURN',
]


def build():
    a = Assembler()
    a.assemble(source())
    lines = list(PROG)
    n = 2000
    for addr, data in a.segments():
        for i in range(0, len(data), 10):
            c = data[i:i + 10]
            lines.append('%d DATA %d,%d,%s' % (n, len(c), addr + i, ','.join(str(b) for b in c)))
            n += 1
    lines.append('%d DATA 0' % n)
    n += 1
    for name, _, _ in ROUTINES:
        lines.append('%d DATA "%s"' % (n, name))
        n += 1
    return a, '\n'.join(lines) + '\n'


def parse_back(text):
    nums = []
    for ln in text.splitlines():
        m = re.match(r'^\d+ DATA (-?\d.*)$', ln)
        if m:
            nums += [int(x) for x in m.group(1).split(',')]
    mem, i = {}, 0
    while nums[i] != 0:
        n, addr = nums[i], nums[i + 1]
        for k in range(n):
            mem[addr + k] = nums[i + 2 + k]
        i += 2 + n
    return mem


def simulate(a):
    import z80_i2c_sim as S
    res = []
    for k in range(len(ROUTINES)):
        hub = S.Hub(S.Slave(0x42))
        cpu = S.Z80(hub)
        for ad, b in a.image.items():
            cpu.mem[ad] = b
        cpu.call(BASE + k * STEP, max_steps=10_000_000)
        res.append((cpu.t * S.US / 1000 / (256 * 10 * OUTER) * 1000, cpu.iff1))
    return res


if __name__ == '__main__':
    a, text = build()
    if '--check' in sys.argv:
        t = open(OUTF).read()
        ok = parse_back(t) == a.image and t == text
        longest = max(len(l) for l in t.splitlines())
        print('DATA = assembler image and file up to date:', ok, '| longest line', longest)
        for (name, _, _), (us, iff) in zip(ROUTINES, simulate(a)):
            print('  %-8s simulator %.3f us per access, interrupts on afterwards: %s' % (name, us, bool(iff)))
        sys.exit(0 if ok and longest <= 80 else 1)
    open(OUTF, 'w').write(text)
    print('written', OUTF, len(text.splitlines()), 'lines')
