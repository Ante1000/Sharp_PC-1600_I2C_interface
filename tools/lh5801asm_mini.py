#!/usr/bin/env python3
"""Minimal LH5801 assembler for the I2C sources (i2c_v1.4.asm of the PC-1500 repository and
asm/i2c_lh_v1.0.asm). Only the instructions of these sources; the encodings were taken from the
listing i2c_v1.4.lst, and --selftest reassembles v1.4 and compares every byte with that listing.

Usage: lh5801asm_mini.py file.asm [-D NAME=VALUE ...] [-l out.lst] [--base ADDR]
       lh5801asm_mini.py --selftest i2c_v1.4.asm i2c_v1.4.lst
Syntax of the sources: LABEL: MNEMONIC operands ; comment. Operands: numbers (12, &1F),
constants (-D), (IP,&FD) = address IP*256+&FD, #(X) / #(Y) / #(&F00F). BCH+/BCS+/BCR+/BZS+/BZR+
= forward, BCH-/... = backward branch, LOP UL,label. Symbols IP, TP, RP, BM, DB are constants.
"""
import re
import sys

SIMPLE = {'RIE': [0xFD, 0xBE], 'SIE': [0xFD, 0x81], 'REC': [0xF9], 'SEC': [0xFB], 'RTN': [0x9A],
          'ROL': [0xDB], 'SHL': [0xD9], 'SPU': [0xE1], 'RPU': [0xE3], 'SPV': [0xA8], 'RPV': [0xB8],
          'NOP': [0x38], 'LDA UL': [0x24], 'STA XL': [0x0A], 'SIN U': [0x61], 'LIN U': [0x65],
          'DCS (X)': [0x0C]}
IMM = {'LDI A': 0xB5, 'LDI XL': 0x4A, 'LDI XH': 0x48, 'LDI YL': 0x5A, 'LDI YH': 0x58,
       'LDI UL': 0x6A, 'LDI UH': 0x68, 'CPI UL': 0x6E}
IMM2 = {'ANI #(X)': [0xFD, 0x49], 'ORI #(X)': [0xFD, 0x4B], 'BII #(X)': [0xFD, 0x4D],
        'ANI #(Y)': [0xFD, 0x59], 'ORI #(Y)': [0xFD, 0x5B]}
IMMABS = {'ANI': [0xFD, 0xE9], 'ORI': [0xFD, 0xEB], 'BII': [0xFD, 0xED]}
ABS = {'LDA': 0xA5, 'STA': 0xAE, 'SJP': 0xBE}
BR = {'BCH': (0x8E, 0x9E), 'BCS': (0x83, 0x93), 'BCR': (0x81, 0x91), 'BZS': (0x8B, 0x9B), 'BZR': (0x89, 0x99)}


class AsmError(Exception):
    pass


def split_ops(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class Asm:
    def __init__(self, consts=None, base=0):
        self.consts = dict(consts or {})
        self.base = base          # address of the first byte (labels are offsets from it)
        self.labels = {}
        self.code = bytearray()
        self.listing = []

    def val(self, tok, final):
        t = tok.strip()
        total, pos = 0, 0
        for sign, w in re.findall(r'([+-]?)\s*(&[0-9A-Fa-f]+|0[xX][0-9A-Fa-f]+|\w+)', t):
            if w in self.consts:
                v = self.consts[w]
            elif w in self.labels:
                v = self.labels[w]
            elif w.startswith('&'):
                v = int(w[1:], 16)
            elif w.lower().startswith('0x'):
                v = int(w, 16)
            elif w.isdigit():
                v = int(w)
            elif final:
                raise AsmError('undefined: ' + w)
            else:
                v = 0
            total += -v if sign == '-' else v
        return total

    def addr16(self, tok, final):
        m = re.fullmatch(r'\((.+)\)', tok.strip())
        inner = m.group(1) if m else tok
        if ',' in inner:
            hi, lo = split_ops(inner)
            v = (self.val(hi, final) << 8) | (self.val(lo, final) & 0xFF)
        else:
            v = self.val(inner, final)
        return v & 0xFFFF

    def encode(self, mn, ops, pc, final):
        key = mn + (' ' + ops[0] if ops else '')
        if key in SIMPLE and len(ops) <= 1:
            return list(SIMPLE[key])
        if mn in SIMPLE and not ops:
            return list(SIMPLE[mn])
        b8 = lambda x: self.val(x, final) & 0xFF
        if mn == 'LDI' and len(ops) == 2 and 'LDI ' + ops[0] in IMM:
            return [IMM['LDI ' + ops[0]], b8(ops[1])]
        if mn == 'CPI' and len(ops) == 2 and 'CPI ' + ops[0] in IMM:
            return [IMM['CPI ' + ops[0]], b8(ops[1])]
        if len(ops) == 2 and mn + ' ' + ops[0] in IMM2:
            return IMM2[mn + ' ' + ops[0]] + [b8(ops[1])]
        if mn in IMMABS and len(ops) == 2 and ops[0].startswith('#(&'):
            a = self.addr16(ops[0][1:], final)
            return IMMABS[mn] + [a >> 8, a & 255, b8(ops[1])]
        if mn in ABS and len(ops) == 1 and ops[0] not in ('UL', 'XL'):
            a = self.addr16(ops[0], final)
            if mn == 'SJP':
                a = ((self.consts['IP'] << 8) | (self.val(ops[0], final) & 0xFF)) if 'IP' in self.consts else a
            return [ABS[mn], a >> 8, a & 255]
        m = re.fullmatch(r'(B[CZ][SRH]|BCH)([+-])', mn)
        if m and len(ops) == 1:
            name, d = m.group(1), m.group(2)
            if name not in BR:
                raise AsmError('branch ' + mn)
            tgt = self.val(ops[0], final)
            nxt = pc + 2
            dist = tgt - nxt if d == '+' else nxt - tgt
            if final and not 0 <= dist <= 255:
                raise AsmError('branch out of range: %s %s (%d)' % (mn, ops[0], dist))
            return [BR[name][0 if d == '+' else 1], dist & 0xFF]
        if mn == 'LOP' and len(ops) == 2:
            dist = (pc + 2) - self.val(ops[1], final)
            if final and not 0 <= dist <= 255:
                raise AsmError('LOP out of range')
            return [0x88, dist & 0xFF]
        raise AsmError('cannot assemble: %s %s' % (mn, ', '.join(ops)))

    def assemble(self, text):
        lines = text.splitlines()
        for final in (False, True):
            pc = 0
            self.code = bytearray()
            self.listing = []
            for ln in lines:
                s = ln.split(';', 1)[0].rstrip()
                label = None
                m = re.match(r'^([A-Za-z_]\w*):', s)
                if m:
                    label = m.group(1)
                    s = s[m.end():]
                s = s.strip()
                if label:
                    self.labels[label] = pc
                if not s:
                    self.listing.append((None, [], ln))
                    continue
                m = re.fullmatch(r'(\w+[+-]?)\s+(.*)', s)
                mn = (m.group(1) if m else s).upper()
                ops = split_ops(m.group(2)) if m else []
                data = self.encode(mn, ops, pc, final)
                self.code += bytes(data)
                self.listing.append((pc, data, ln))
                pc += len(data)
        return bytes(self.code)

    def list_text(self):
        out = []
        for pc, data, ln in self.listing:
            out.append(' ' * 22 + ln if pc is None else '%02X  %-14s %s' % (pc, ' '.join('%02X' % b for b in data), ln))
        return '\n'.join(out) + '\n'


def selftest(asm_path, lst_path):
    consts = {'IP': 0x44, 'TP': 0x43, 'RP': 0x42, 'BM': 4, 'DB': 0xFB}
    a = Asm(consts)
    code = a.assemble(open(asm_path).read())
    want = bytearray()
    for ln in open(lst_path):
        if not re.match(r'^[0-9A-F]{2}  ', ln):
            continue
        for tok in ln[4:19].split():        # the byte field of the listing
            # 'DB' is the hex byte of ROL and also the symbol DB: it is the symbol only as an operand (",DB")
            sym = tok in consts and (tok != 'DB' or ',DB' in ln[19:])
            want.append(consts[tok] if sym else int(tok, 16))
    ok = bytes(want) == code
    print('v1.4 reassembled: %d bytes, listing %d bytes, identical: %s' % (len(code), len(want), ok))
    if not ok:
        for i, (x, y) in enumerate(zip(code, want)):
            if x != y:
                print('first difference at %02X: %02X vs %02X' % (i, x, y))
                break
    return 0 if ok else 1


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == '--selftest':
        sys.exit(selftest(args[1], args[2]))
    consts, lst, src = {}, None, None
    i = 0
    while i < len(args):
        if args[i] == '-D':
            k, v = args[i + 1].split('=')
            consts[k] = int(v, 0)
            i += 2
        elif args[i] == '-l':
            lst = args[i + 1]
            i += 2
        else:
            src = args[i]
            i += 1
    a = Asm(consts)
    code = a.assemble(open(src).read())
    if lst:
        open(lst, 'w').write(a.list_text())
    print('%d bytes: %s' % (len(code), code.hex()))
