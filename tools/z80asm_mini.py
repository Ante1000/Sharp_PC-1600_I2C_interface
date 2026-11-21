#!/usr/bin/env python3
"""Minimal Z80 assembler, only for the instruction subset used by i2c_z80_*.asm.

Usage: z80asm_mini.py file.asm [-l file.lst]
Syntax: LABEL: MNEMONIC operands ; comment, ORG, EQU, DB, numbers as 12, 0C100h, 0x1F.
Unknown instructions are an error, so nothing is silently mis-assembled.
"""
import re
import sys

R8 = {'B': 0, 'C': 1, 'D': 2, 'E': 3, 'H': 4, 'L': 5, 'A': 7}
CC = {'NZ': 0, 'Z': 1, 'NC': 2, 'C': 3, 'PO': 4, 'PE': 5, 'P': 6, 'M': 7}


class AsmError(Exception):
    pass


def split_operands(s):
    ops, depth, cur = [], 0, ''
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            ops.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        ops.append(cur.strip())
    return ops


class Assembler:
    def __init__(self):
        self.sym = {}
        self.image = {}      # addr -> byte
        self.listing = []    # (addr, bytes, source line)

    # ---- expressions -------------------------------------------------
    def ev(self, expr, pc, final):
        e = expr.strip()

        def num(m):
            t = m.group(0)
            if re.fullmatch(r'0[xX][0-9A-Fa-f]+', t):
                return str(int(t, 16))
            if re.fullmatch(r'[0-9][0-9A-Fa-f]*[hH]', t):
                return str(int(t[:-1], 16))
            return t
        e = re.sub(r'0[xX][0-9A-Fa-f]+|[0-9][0-9A-Fa-f]*[hH]', num, e)

        def name(m):
            n = m.group(0)
            if n == '$':
                return str(pc)
            if n in self.sym:
                return str(self.sym[n])
            if final:
                raise AsmError('undefined symbol ' + n)
            return '0'
        e = re.sub(r'[A-Za-z_][A-Za-z0-9_]*', name, e)
        if not re.fullmatch(r'[0-9+\-*()\s<>&|]*', e):
            raise AsmError('bad expression ' + expr)
        return eval(e)

    # ---- instruction encoding ---------------------------------------
    def encode(self, mn, ops, pc, final):
        ev = lambda x: self.ev(x, pc, final)
        up = [o.upper() for o in ops]
        n = len(ops)

        def imm8(x):
            v = ev(x)
            if final and not -128 <= v <= 255:
                raise AsmError('8-bit value out of range: %s' % x)
            return v & 0xFF

        def imm16(x):
            return ev(x) & 0xFFFF

        def rel(x):
            d = ev(x) - (pc + 2)
            if final and not -128 <= d <= 127:
                raise AsmError('relative jump out of range: %s (%d)' % (x, d))
            return d & 0xFF

        if mn == 'NOP' and n == 0: return [0x00]
        if mn == 'DI' and n == 0: return [0xF3]
        if mn == 'EI' and n == 0: return [0xFB]
        if mn == 'SCF' and n == 0: return [0x37]
        if mn == 'RET' and n == 0: return [0xC9]
        if mn == 'RRA' and n == 0: return [0x1F]
        if mn == 'PUSH' and up == ['AF']: return [0xF5]
        if mn == 'POP' and up == ['AF']: return [0xF1]
        if mn == 'XOR' and up == ['A']: return [0xAF]
        if mn == 'OR' and up == ['A']: return [0xB7]
        if mn == 'ADD' and up == ['A', 'A']: return [0x87]
        if mn == 'AND' and n == 1: return [0xE6, imm8(ops[0])]
        if mn == 'RLC' and n == 1 and up[0] in R8: return [0xCB, 0x00 + R8[up[0]]]
        if mn == 'RL' and n == 1 and up[0] in R8: return [0xCB, 0x10 + R8[up[0]]]
        if mn == 'BIT' and n == 2 and up[1] in R8:
            return [0xCB, 0x40 + 8 * ev(ops[0]) + R8[up[1]]]
        if mn == 'INC' and n == 1:
            if up[0] in R8: return [0x04 + 8 * R8[up[0]]]
            if up[0] == 'HL': return [0x23]
        if mn == 'DEC' and n == 1 and up[0] in R8: return [0x05 + 8 * R8[up[0]]]
        if mn == 'DJNZ' and n == 1: return [0x10, rel(ops[0])]
        if mn == 'JR':
            if n == 1: return [0x18, rel(ops[0])]
            if n == 2 and up[0] in ('NZ', 'Z', 'NC', 'C'):
                return [0x20 + 8 * CC[up[0]], rel(ops[1])]
        if mn == 'JP':
            if n == 1: return [0xC3] + list(imm16(ops[0]).to_bytes(2, 'little'))
            if n == 2 and up[0] in CC:
                return [0xC2 + 8 * CC[up[0]]] + list(imm16(ops[1]).to_bytes(2, 'little'))
        if mn == 'CALL' and n == 1: return [0xCD] + list(imm16(ops[0]).to_bytes(2, 'little'))
        if mn == 'OUT' and n == 2 and up[1] == 'A' and ops[0].startswith('('):
            return [0xD3, imm8(ops[0][1:-1])]
        if mn == 'IN' and n == 2 and up[0] == 'A' and ops[1].startswith('('):
            return [0xDB, imm8(ops[1][1:-1])]
        if mn == 'LD' and n == 2:
            d, s = up
            if d == 'I' and s == 'A': return [0xED, 0x47]
            if d == 'A' and s == 'I': return [0xED, 0x57]
            if d in R8 and s in R8: return [0x40 + 8 * R8[d] + R8[s]]
            if d in R8 and s == '(HL)': return [0x46 + 8 * R8[d]]
            if d == '(HL)' and s in R8: return [0x70 + R8[s]]
            if d == 'HL' and not ops[1].startswith('('):
                return [0x21] + list(imm16(ops[1]).to_bytes(2, 'little'))
            if d == 'A' and ops[1].startswith('(') and ops[1].endswith(')') and s != '(HL)':
                return [0x3A] + list(imm16(ops[1][1:-1]).to_bytes(2, 'little'))
            if ops[0].startswith('(') and s == 'A' and d != '(HL)':
                return [0x32] + list(imm16(ops[0][1:-1]).to_bytes(2, 'little'))
            if d in R8 and not ops[1].startswith('('):
                return [0x06 + 8 * R8[d], imm8(ops[1])]
        raise AsmError('cannot assemble: %s %s' % (mn, ', '.join(ops)))

    # ---- driver -------------------------------------------------------
    def parse(self, line):
        line = line.split(';', 1)[0].rstrip()
        label = None
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):', line)
        if m:
            label = m.group(1)
            line = line[m.end():]
        m = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(EQU|equ)\s+(.*)$', line)
        if m and not label:
            return m.group(1), 'EQU', [m.group(3).strip()]
        line = line.strip()
        if not line:
            return label, None, []
        parts = line.split(None, 1)
        mn = parts[0].upper()
        ops = split_operands(parts[1]) if len(parts) > 1 else []
        return label, mn, ops

    def assemble(self, text):
        lines = text.splitlines()
        for final in (False, True):
            pc = 0
            self.image = {}
            self.listing = []
            for ln in lines:
                label, mn, ops = self.parse(ln)
                if mn == 'EQU':
                    self.sym[label] = self.ev(ops[0], pc, final)
                    self.listing.append((None, [], ln))
                    continue
                if label:
                    self.sym[label] = pc
                if mn is None:
                    self.listing.append((None, [], ln))
                    continue
                if mn == 'ORG':
                    pc = self.ev(ops[0], pc, final)
                    self.listing.append((None, [], ln))
                    continue
                if mn == 'DB':
                    data = [self.ev(o, pc, final) & 0xFF for o in ops]
                else:
                    data = self.encode(mn, ops, pc, final)
                if final:
                    for i, b in enumerate(data):
                        if pc + i in self.image:
                            raise AsmError('overlap at %04X' % (pc + i))
                        self.image[pc + i] = b
                self.listing.append((pc, data, ln))
                pc += len(data)
        return self.image

    def segments(self):
        segs, cur = [], None
        for a in sorted(self.image):
            if cur and a == cur[0] + len(cur[1]):
                cur[1].append(self.image[a])
            else:
                cur = [a, [self.image[a]]]
                segs.append(cur)
        return segs

    def list_text(self):
        out = []
        for pc, data, ln in self.listing:
            if pc is None:
                out.append(' ' * 18 + ln)
            else:
                hexs = ' '.join('%02X' % b for b in data)
                out.append('%04X  %-12s %s' % (pc, hexs, ln))
        return '\n'.join(out) + '\n'


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('-l', '--lst')
    a = ap.parse_args()
    asm = Assembler()
    try:
        asm.assemble(open(a.src).read())
    except AsmError as e:
        sys.exit('error: %s' % e)
    if a.lst:
        open(a.lst, 'w').write(asm.list_text())
    segs = asm.segments()
    for addr, data in segs:
        print('%04X-%04X  %d bytes' % (addr, addr + len(data) - 1, len(data)))
