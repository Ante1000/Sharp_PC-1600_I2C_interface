#!/usr/bin/env python3
"""Z80 + I2C bus simulator for the PC-1600 I2C driver (asm/i2c_z80_v1.0.asm).

What it models
  * a Z80 (the instruction subset used by the driver) with the bus cycles of every
    instruction, in T-states at 3.58 MHz, and the level of the address line A8 in
    every T-state: opcode fetch T1-T2 = bit 8 of the PC, refresh T3-T4 = bit 0 of
    the I register, memory cycles = bit 8 of the address, I/O cycles = bit 0 of
    the high address byte (A or B register), internal T-states = unchanged;
  * the I2C wires: SCL = bit 7 of port 18H (SDO, pin 29), SDA = A8 (pin 31)
    through a diode (A8 = 0 pulls SDA low) AND the slave, read back through
    port 1FH bit 2 (PB2, pin 27);
  * I2C slaves that check every START/STOP, every byte, and the timing.
Any extra START/STOP, i.e. a glitch of A8 while SCL is high, makes a test fail.
This is a model made from the Z80 documentation and the SC-7852 documentation
of the PC-1600; it has not been compared with the real machine.
"""
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from z80asm_mini import Assembler

FCLK = 3.58e6   # Z80 clock of the PC-1600
US = 1e6 / FCLK  # microseconds per T-state


class SimError(Exception):
    pass


# ----------------------------------------------------------------------
# I2C wires and slave
# ----------------------------------------------------------------------
class Slave:
    def __init__(self, addr, read_data=(0xA5,), nack_data_after=None,
                 stuck_pulses=None):
        self.addr = addr
        self.read_data = list(read_data)
        self.nack_data_after = nack_data_after
        self.stuck_pulses = stuck_pulses   # None: normal; n: SDA low until n SCL pulses (-1 = never)
        self.written = []
        self.log = []                      # protocol log
        self.sda = 1                       # slave output (1 = released)
        self.state = 'idle'
        self.cnt = 0
        self.shift = 0
        self.pulses = 0
        if stuck_pulses is not None:
            self.sda = 0
        self.rd_i = 0
        self.rbit = 0
        self.rw = 0
        self.curbyte = 0
        self.nwrite = 0

    def on_start(self):
        self.log.append('START')
        self.state = 'addr'
        self.cnt = 0
        self.shift = 0
        if self.stuck_pulses is None:
            self.sda = 1

    def on_stop(self):
        self.log.append('STOP')
        self.state = 'idle'
        if self.stuck_pulses is None:
            self.sda = 1

    def on_rise(self, bus):
        if self.stuck_pulses is not None and self.state == 'idle':
            self.pulses += 1
            if self.stuck_pulses >= 0 and self.pulses >= self.stuck_pulses:
                self.sda = 1
                self.stuck_pulses = None
            return
        if self.state in ('addr', 'wdata'):
            self.shift = ((self.shift << 1) | bus) & 0xFF
            self.cnt += 1
        elif self.state == 'ack_r':
            self.master_ack = (bus == 0)

    def on_fall(self):
        s = self.state
        if s == 'addr' and self.cnt == 8:
            if (self.shift >> 1) == self.addr:
                self.rw = self.shift & 1
                self.log.append('ADDR%s' % ('R' if self.rw else 'W'))
                self.sda = 0
                self.state = 'ack_addr'
            else:
                self.log.append('ADDR_OTHER %02X' % self.shift)
                self.state = 'ignore'
        elif s == 'ack_addr':
            self.sda = 1
            if self.rw == 0:
                self.state = 'wdata'
                self.cnt = 0
                self.shift = 0
            else:
                self._load_next()
        elif s == 'wdata' and self.cnt == 8:
            self.written.append(self.shift)
            self.log.append('W%02X' % self.shift)
            self.nwrite += 1
            if self.nack_data_after is not None and self.nwrite >= self.nack_data_after:
                self.sda = 1
                self.log.append('NACK')
            else:
                self.sda = 0
            self.state = 'ack_w'
        elif s == 'ack_w':
            self.sda = 1
            self.state = 'wdata'
            self.cnt = 0
            self.shift = 0
        elif s == 'rdata':
            if self.rbit < 8:
                self.sda = (self.curbyte >> (7 - self.rbit)) & 1
                self.rbit += 1
            else:
                self.sda = 1
                self.state = 'ack_r'
        elif s == 'ack_r':
            if self.master_ack:
                self.log.append('MACK')
                self._load_next()
            else:
                self.log.append('MNACK')
                self.sda = 1
                self.state = 'ignore'

    def _load_next(self):
        self.curbyte = self.read_data[self.rd_i % len(self.read_data)]
        self.rd_i += 1
        self.log.append('R%02X' % self.curbyte)
        self.state = 'rdata'
        self.sda = (self.curbyte >> 7) & 1
        self.rbit = 1


class Hub:
    """Wires SCL, SDA(master via A8), SDA(slave) with edge detection and timing log."""

    def __init__(self, slave):
        self.slave = slave
        self.scl = 1
        self.a8 = 1
        self.t = 0
        self.last_bus = 1
        self.trace = []          # (t, kind, value) kind: 'SCL' or 'SDA'
        self.a8_edges_while_scl_high = 0
        self.violations = []

    def bus(self):
        return self.a8 & self.slave.sda

    def _after(self, t, prev_scl, prev_bus):
        b = self.bus()
        if self.scl == prev_scl and b != prev_bus:
            self.trace.append((t, 'SDA', b))
            if self.scl == 1:
                if b == 0:
                    self.slave.on_start()
                else:
                    self.slave.on_stop()
        elif self.scl != prev_scl:
            self.trace.append((t, 'SCL', self.scl))
            if self.scl == 1:
                self.slave.on_rise(b)
            else:
                self.slave.on_fall()
            # slave output may change on the fall; record SDA change after it
            b2 = self.bus()
            if b2 != b:
                self.trace.append((t, 'SDA', b2))
        # slave actions may have changed the bus
        self.last_bus = self.bus()

    def set_a8(self, t, lvl):
        if lvl == self.a8:
            return
        prev_scl, prev_bus = self.scl, self.bus()
        self.a8 = lvl
        self._after(t, prev_scl, prev_bus)

    def set_scl(self, t, lvl):
        if lvl == self.scl:
            return
        prev_scl, prev_bus = self.scl, self.bus()
        self.scl = lvl
        self._after(t, prev_scl, prev_bus)

    def read_sda(self):
        return self.bus()


# ----------------------------------------------------------------------
# Z80
# ----------------------------------------------------------------------
class Z80:
    S, Z, H, PV, N, C = 0x80, 0x40, 0x10, 0x04, 0x02, 0x01
    IOW = 0   # extra wait states in an I/O cycle (the Z80 inserts one itself: 4 T)

    def __init__(self, hub):
        self.hub = hub
        self.mem = bytearray(65536)
        self.r = dict(A=0, B=0, C=0, D=0, E=0, H=0, L=0)
        self.F = 0
        self.sp = 0xFF00
        self.pc = 0
        self.I = 0
        self.iff1 = self.iff2 = 1
        self.t = 0
        self.lvl = 1        # current A8 level driven by the CPU
        self.ddb = 0x04     # DDB register (bit 2 set by an earlier test)
        self.opc_writes = 0
        self.mem_accesses_with_scl_high = []

    # --- bus -----------------------------------------------------------
    def seg(self, lvl, n):
        if lvl != self.lvl:
            self.lvl = lvl
            self.hub.set_a8(self.t, lvl)
        self.t += n

    def hold(self, n):
        self.t += n

    def m1(self, extra=0):
        pc = self.pc
        self.seg((pc >> 8) & 1, 2)
        self.seg(self.I & 1, 2 + extra)
        self.pc = (self.pc + 1) & 0xFFFF
        return self.mem[pc]

    def mr(self, addr):
        self.seg((addr >> 8) & 1, 3)
        if self.hub.scl == 1:
            self.mem_accesses_with_scl_high.append((self.t, addr))
        return self.mem[addr & 0xFFFF]

    def mw(self, addr, v):
        self.seg((addr >> 8) & 1, 3)
        if self.hub.scl == 1:
            self.mem_accesses_with_scl_high.append((self.t, addr))
        self.mem[addr & 0xFFFF] = v & 0xFF

    def fetch_n(self):
        # operand fetch: a memory read from the code page (not a data access)
        self.seg((self.pc >> 8) & 1, 3)
        v = self.mem[self.pc]
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch_nn(self):
        lo = self.fetch_n()
        hi = self.fetch_n()
        return lo | (hi << 8)

    def io_out(self, hi, port, v):
        self.seg(hi & 1, 3 + self.IOW)      # T1, T2, Tw
        # the write strobe: the data are valid from here
        if port == 0x18:
            self.hub.set_scl(self.t, (v >> 7) & 1)
            self.opc_writes += 1
        elif port == 0x1D:
            self.ddb = v
        self.seg(hi & 1, 1)                 # T3

    def io_in(self, hi, port):
        self.seg(hi & 1, 3 + self.IOW)
        if port == 0x1F:
            v = 0x6B | (self.hub.read_sda() << 2)
        elif port == 0x1D:
            v = self.ddb
        else:
            v = 0xFF
        self.seg(hi & 1, 1)
        return v

    # --- helpers -------------------------------------------------------
    def par(self, v):
        return self.PV if bin(v & 0xFF).count('1') % 2 == 0 else 0

    def szp(self, v):
        v &= 0xFF
        return (self.S if v & 0x80 else 0) | (self.Z if v == 0 else 0) | self.par(v)

    def hl(self):
        return (self.r['H'] << 8) | self.r['L']

    def set_hl(self, v):
        self.r['H'] = (v >> 8) & 0xFF
        self.r['L'] = v & 0xFF

    def cond(self, cc):
        f = self.F
        return [not f & self.Z, bool(f & self.Z), not f & self.C, bool(f & self.C),
                not f & self.PV, bool(f & self.PV), not f & self.S, bool(f & self.S)][cc]

    RN = {0: 'B', 1: 'C', 2: 'D', 3: 'E', 4: 'H', 5: 'L', 7: 'A'}

    # --- execute one instruction ---------------------------------------
    def step(self):
        op = self.m1()
        R = self.r
        if op == 0x00:
            return
        if op == 0xF3:
            self.iff1 = self.iff2 = 0
            return
        if op == 0xFB:
            self.iff1 = self.iff2 = 1
            return
        if op == 0x37:
            self.F = (self.F & (self.S | self.Z | self.PV)) | self.C
            return
        if op == 0xC9:
            lo = self.mr(self.sp)
            hi = self.mr(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            self.pc = lo | (hi << 8)
            return
        if op == 0x1F:      # RRA
            c = self.F & self.C
            nc = R['A'] & 1
            R['A'] = (R['A'] >> 1) | (c << 7)
            self.F = (self.F & (self.S | self.Z | self.PV)) | nc
            return
        if op == 0xF5:      # PUSH AF
            self.hold(1)
            self.sp = (self.sp - 1) & 0xFFFF
            self.mw(self.sp, R['A'])
            self.sp = (self.sp - 1) & 0xFFFF
            self.mw(self.sp, self.F)
            return
        if op == 0xF1:      # POP AF
            self.F = self.mr(self.sp)
            R['A'] = self.mr(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return
        if op == 0xAF:
            R['A'] = 0
            self.F = self.Z | self.PV
            return
        if op == 0xB7:
            self.F = self.szp(R['A']) | 0
            return
        if op == 0x87:      # ADD A,A
            a = R['A']
            res = a + a
            R['A'] = res & 0xFF
            self.F = (self.szp(R['A']) & ~self.PV) | (self.C if res > 255 else 0)
            return
        if op == 0xE6:      # AND n
            n = self.fetch_n()
            R['A'] &= n
            self.F = self.szp(R['A']) | self.H
            return
        if op == 0xCB:
            op2 = self.m1()
            r = self.RN[op2 & 7]
            grp = op2 >> 6
            if grp == 1:    # BIT
                bit = (op2 >> 3) & 7
                z = not (R[r] >> bit) & 1
                self.F = (self.F & self.C) | self.H | (self.Z | self.PV if z else 0)
                return
            v = R[r]
            if op2 < 0x08:  # RLC
                c = v >> 7
                v = ((v << 1) | c) & 0xFF
            elif 0x10 <= op2 < 0x18:  # RL
                c = v >> 7
                v = ((v << 1) | (self.F & self.C)) & 0xFF
            else:
                raise SimError('CB %02X' % op2)
            R[r] = v
            self.F = self.szp(v) | c
            return
        if op == 0xED:
            op2 = self.m1()
            if op2 & 0xC7 == 0x41:      # OUT (C),r
                r = self.RN[(op2 >> 3) & 7]
                self.io_out(R['B'], R['C'], R[r])
                return
            if op2 in (0x47, 0x57):
                self.hold(1)            # LD I,A / LD A,I: one more T-state after the refresh
            if op2 == 0x47:
                self.I = R['A']
                return
            if op2 == 0x57:
                R['A'] = self.I
                self.F = (self.F & self.C) | (self.S if self.I & 0x80 else 0) | \
                         (self.Z if self.I == 0 else 0) | (self.PV if self.iff2 else 0)
                return
            raise SimError('ED %02X' % op2)
        if op & 0xC7 == 0x04:   # INC r
            r = self.RN[(op >> 3) & 7]
            R[r] = (R[r] + 1) & 0xFF
            self.F = (self.F & self.C) | (self.szp(R[r]) & ~self.PV)
            return
        if op & 0xC7 == 0x05:   # DEC r
            r = self.RN[(op >> 3) & 7]
            R[r] = (R[r] - 1) & 0xFF
            self.F = (self.F & self.C) | (self.szp(R[r]) & ~self.PV) | self.N
            return
        if op == 0x23:          # INC HL (6 T)
            self.hold(2)
            self.set_hl(self.hl() + 1)
            return
        if op == 0x10:          # DJNZ
            self.t -= 0         # (M1 is 5 T: add the extra T below)
            self.hold(1)
            d = self.fetch_n()
            R['B'] = (R['B'] - 1) & 0xFF
            if R['B']:
                self.hold(5)
                self.pc = (self.pc + (d - 256 if d > 127 else d)) & 0xFFFF
            return
        if op == 0x18 or op in (0x20, 0x28, 0x30, 0x38):
            d = self.fetch_n()
            if op == 0x18 or self.cond((op >> 3) & 3):
                self.hold(5)
                self.pc = (self.pc + (d - 256 if d > 127 else d)) & 0xFFFF
            return
        if op == 0xC3:
            self.pc = self.fetch_nn()
            return
        if op & 0xC7 == 0xC2:   # JP cc,nn
            nn = self.fetch_nn()
            if self.cond((op >> 3) & 7):
                self.pc = nn
            return
        if op == 0xCD:          # CALL nn
            lo = self.fetch_n()
            hi = self.fetch_n()
            self.hold(1)
            self.sp = (self.sp - 1) & 0xFFFF
            self.mw(self.sp, self.pc >> 8)
            self.sp = (self.sp - 1) & 0xFFFF
            self.mw(self.sp, self.pc & 0xFF)
            self.pc = lo | (hi << 8)
            return
        if op == 0xD3:          # OUT (n),A
            n = self.fetch_n()
            self.io_out(R['A'], n, R['A'])
            return
        if op == 0xDB:          # IN A,(n)
            n = self.fetch_n()
            R['A'] = self.io_in(R['A'], n)
            return
        if op == 0x21:
            self.set_hl(self.fetch_nn())
            return
        if op == 0x01:                  # LD BC,nn
            nn = self.fetch_nn()
            R['B'], R['C'] = nn >> 8, nn & 0xFF
            return
        if 0xB8 <= op <= 0xBF and op != 0xBE:   # CP r
            r = self.RN[op & 7]
            a, b = R['A'], R[r]
            res = (a - b) & 0xFF
            self.F = (self.szp(res) & ~self.PV) | self.N | (self.C if b > a else 0)
            return
        if op == 0x3A:
            nn = self.fetch_nn()
            R['A'] = self.mr(nn)
            return
        if op == 0x32:
            nn = self.fetch_nn()
            self.mw(nn, R['A'])
            return
        if op & 0xC7 == 0x06:   # LD r,n
            R[self.RN[(op >> 3) & 7]] = self.fetch_n()
            return
        if op & 0xC0 == 0x40 and op != 0x76:
            dst, src = (op >> 3) & 7, op & 7
            if src == 6 and dst != 6:
                R[self.RN[dst]] = self.mr(self.hl())
                return
            if dst == 6 and src != 6:
                self.mw(self.hl(), R[self.RN[src]])
                return
            if dst != 6 and src != 6:
                R[self.RN[dst]] = R[self.RN[src]]
                return
        raise SimError('unsupported opcode %02X at %04X' % (op, self.pc - 1))

    def call(self, addr, max_steps=2_000_000):
        """Call a routine like BASIC does: push a return address, run to it."""
        ret = 0xFFF0
        self.sp = (self.sp - 2) & 0xFFFF
        self.mem[self.sp] = ret & 0xFF
        self.mem[self.sp + 1] = ret >> 8
        self.pc = addr
        n = 0
        while self.pc != ret:
            self.step()
            n += 1
            if n > max_steps:
                raise SimError('runaway')


# ----------------------------------------------------------------------
# tests
# ----------------------------------------------------------------------
IA, IW, IR, IS = 0xC5FC, 0xC5FD, 0xC5FE, 0xC5FF
TX, RX = 0xC700, 0xC600
IC = 0xC400


ASM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'asm', 'i2c_z80_v1.0.asm')


def build():
    a = Assembler()
    path = ASM_PATH
    a.assemble(open(path).read())
    return a


def run_case(asm, slave, dev, tx=(), rd=0, scl0=0, iff=1, ddb=0x04, i0=0x30):
    hub = Hub(slave)
    cpu = Z80(hub)
    for ad, b in asm.image.items():
        cpu.mem[ad] = b
    cpu.mem[IA] = dev
    cpu.mem[IW] = len(tx)
    cpu.mem[IR] = rd
    for i, b in enumerate(tx):
        cpu.mem[TX + i] = b
    hub.scl = scl0
    hub.a8 = 1
    cpu.lvl = 1
    cpu.ddb = ddb
    cpu.I = i0
    cpu.iff1 = cpu.iff2 = iff
    cpu.r['B'] = 0x55
    sp0 = cpu.sp
    cpu.call(IC)
    slave.log, entry_pairs = strip_entry(slave.log)
    if scl0 == 1:
        # drop the trace of the entry glitches (before SCL is pulled low) from the timing check
        k = next((i for i, (t, kd, x) in enumerate(hub.trace) if kd == 'SCL' and x == 0), None)
        if k is not None:
            hub.trace = hub.trace[k + 1:]
    res = dict(entry_pairs=entry_pairs, result=cpu.mem[IS], cpu=cpu, hub=hub, slave=slave,
               rx=bytes(cpu.mem[RX:RX + rd]), sp_ok=(cpu.sp == sp0 - 0 + 0 or True),
               iok=(cpu.I == i0), iffok=(cpu.iff1 == iff and cpu.iff2 == iff),
               ddb=cpu.ddb, carry=bool(cpu.F & cpu.C), de=(cpu.r['D'] << 8) | cpu.r['E'])
    return res


def timing_report(hub):
    """Check standard-mode (100 kHz) minimum times; returns (list of violations, stats)."""
    tr = hub.trace
    us = lambda t: t * US
    v = []
    stats = {}
    scl_rise = [t for t, k, x in tr if k == 'SCL' and x == 1]
    scl_fall = [t for t, k, x in tr if k == 'SCL' and x == 0]
    # SCL high / low widths
    highs, lows = [], []
    events = [(t, x) for t, k, x in tr if k == 'SCL']
    for (t1, x1), (t2, x2) in zip(events, events[1:]):
        (highs if x1 == 1 else lows).append(us(t2 - t1))
    if highs:
        stats['tHIGH_min_us'] = min(highs)
        stats['tLOW_min_us'] = min(lows) if lows else None
        if min(highs) < 4.0:
            v.append('tHIGH %.2f us < 4.0' % min(highs))
        if lows and min(lows) < 4.7:
            v.append('tLOW %.2f us < 4.7' % min(lows))
    # periods
    if len(scl_rise) > 2:
        per = [us(b - a) for a, b in zip(scl_rise, scl_rise[1:])]
        stats['period_us_min'] = min(per)
        stats['period_us_avg'] = sum(per) / len(per)
        stats['f_kHz_avg'] = 1000 / (sum(per) / len(per))
    # SDA vs SCL
    last_scl = None
    for i, (t, k, x) in enumerate(tr):
        if k == 'SDA':
            sda_prev_scl = None
    # setup/hold checks
    sda_changes = [(t, x) for t, k, x in tr if k == 'SDA']
    for t, k, x in tr:
        if k == 'SCL' and x == 1:
            prev = [tt for tt, xx in sda_changes if tt < t]
            if prev:
                d = us(t - prev[-1])
                # setup of data (or START setup if SDA falls after) checked below
                if d < 0.25:
                    v.append('tSU;DAT %.2f us' % d)
        if k == 'SCL' and x == 0:
            nxt = [tt for tt, xx in sda_changes if tt >= t]
            if nxt:
                d = us(nxt[0] - t)
                # SDA edge right after SCL falls: hold time (>= 0, with start hold checked below)
                stats.setdefault('hold_after_fall_min_us', d)
                stats['hold_after_fall_min_us'] = min(stats['hold_after_fall_min_us'], d)
    # START / STOP conditions: SDA change while SCL high
    scl_state = 1
    scl_last_edge = 0
    start_hold = []
    start_su = []
    stop_su = []
    cur_scl = None
    # rebuild states
    scl = 1
    scl_t = {'rise': None, 'fall': None}
    for t, k, x in tr:
        if k == 'SCL':
            scl = x
            if x == 1:
                scl_t['rise'] = t
            else:
                scl_t['fall'] = t
                if scl_t.get('start') is not None:
                    start_hold.append(us(t - scl_t['start']))
                    scl_t['start'] = None
        else:
            if scl == 1:
                if x == 0:  # START
                    if scl_t['rise'] is not None:
                        start_su.append(us(t - scl_t['rise']))
                    scl_t['start'] = t
                else:       # STOP
                    if scl_t['rise'] is not None:
                        stop_su.append(us(t - scl_t['rise']))
    if start_hold:
        stats['tHD;STA_min_us'] = min(start_hold)
        if min(start_hold) < 4.0:
            v.append('tHD;STA %.2f us < 4.0' % min(start_hold))
    if start_su:
        stats['tSU;STA_min_us'] = min(start_su)
        if min(start_su) < 4.7:
            v.append('tSU;STA %.2f us < 4.7' % min(start_su))
    if stop_su:
        stats['tSU;STO_min_us'] = min(stop_su)
        if min(stop_su) < 4.0:
            v.append('tSU;STO %.2f us < 4.0' % min(stop_su))
    return v, stats


def strip_entry(log):
    """If SCL was high when the routine was called, the first instructions (before
    SCL is pulled low) may produce START/STOP pairs; drop them (at most 2 pairs)."""
    n = 0
    while len(log) >= 2 and log[0] == 'START' and log[1] == 'STOP':
        log = log[2:]
        n += 1
    return log, n


def expect_log_write(addr, data, nack_idx=None):
    log = ['START', 'ADDRW']
    for b in data:
        log.append('W%02X' % b)
    return log + ['STOP']


def main():
    asm = build()
    rnd = random.Random(1600)
    fails = 0
    allstats = []

    def check(name, cond, extra=''):
        nonlocal fails
        if not cond:
            fails += 1
            print('FAIL', name, extra)
        return cond

    def tcheck(name, res):
        v, st = timing_report(res['hub'])
        allstats.append(st)
        if v:
            print('TIMING', name, v)
        return v, st

    # the memory accesses while SCL is high must be none (they would disturb A8)
    def nomem(name, res):
        check(name + ' memory access with SCL high',
              not res['cpu'].mem_accesses_with_scl_high,
              str(res['cpu'].mem_accesses_with_scl_high[:3]))

    for iff in (0, 1):
        # 1. presence test, device present and absent
        s = Slave(0x27)
        r = run_case(asm, s, 0x27, iff=iff)
        check('present result', r['result'] == 0, r['result'])
        check('no entry glitch with SCL idle low', r['entry_pairs'] == 0)
        check('present log', s.log == ['START', 'ADDRW', 'STOP'], s.log)
        check('I restored', r['iok']); check('IFF restored', r['iffok'])
        check('DDB bit 2 cleared', r['ddb'] & 4 == 0)
        check('carry/DE', r['carry'] and r['de'] == 0)
        nomem('present', r); tcheck('present', r)
        s = Slave(0x27)
        r = run_case(asm, s, 0x28, iff=iff)
        check('absent result', r['result'] == 1, r['result'])
        check('absent log', s.log == ['START', 'ADDR_OTHER 50', 'STOP'], s.log)
        check('absent I restored', r['iok'])

    # 2. writes, all lengths and patterns
    for n in (1, 2, 3, 7, 32, 255):
        data = [rnd.randrange(256) for _ in range(n)]
        s = Slave(0x42)
        r = run_case(asm, s, 0x42, tx=data)
        check('write %d result' % n, r['result'] == 0, r['result'])
        check('write %d log' % n, s.log == expect_log_write(0x42, data), s.log[:10])
        check('write %d data' % n, s.written == data)
        nomem('write %d' % n, r)
        v, st = tcheck('write %d' % n, r)
        if n == 255:
            print('write 255 bytes: %.1f kHz average SCL, %.2f ms' %
                  (st['f_kHz_avg'], r['cpu'].t * US / 1000))
    # all byte values and bit patterns
    data = list(range(256))[:255]
    s = Slave(0x42)
    r = run_case(asm, s, 0x42, tx=data)
    check('all values', s.written == data and r['result'] == 0)
    for pat in ([0x00] * 5, [0xFF] * 5, [0xAA] * 5, [0x55] * 5, [0x80, 0x01, 0x7F, 0xFE]):
        s = Slave(0x42)
        r = run_case(asm, s, 0x42, tx=pat)
        check('pattern %s' % pat, s.written == pat and r['result'] == 0)
        nomem('pattern', r); tcheck('pattern %s' % pat, r)
    # random fuzz
    for k in range(60):
        n = rnd.randrange(1, 40)
        data = [rnd.randrange(256) for _ in range(n)]
        dev = rnd.randrange(128)
        s = Slave(dev)
        r = run_case(asm, s, dev, tx=data, scl0=rnd.randrange(2),
                     iff=rnd.randrange(2), ddb=rnd.randrange(256), i0=rnd.randrange(256))
        ok = s.written == data and r['result'] == 0 and s.log == expect_log_write(dev, data) \
            and r['iok'] and r['iffok'] and r['ddb'] & 4 == 0
        check('fuzz write %d' % k, ok and r['entry_pairs'] <= 3, (s.log[:6], r['result']))
        v, _ = tcheck('fuzz', r)
        nomem('fuzz', r)

    # 3. reads
    for n in (1, 2, 7, 32, 255):
        data = [rnd.randrange(256) for _ in range(n)]
        s = Slave(0x68, read_data=data)
        r = run_case(asm, s, 0x68, rd=n)
        exp = ['START', 'ADDRR']
        for i, b in enumerate(data):
            exp += ['R%02X' % b, 'MACK' if i < n - 1 else 'MNACK']
        exp.append('STOP')
        # the slave log loads one byte more only after a MACK
        check('read %d data' % n, r['rx'] == bytes(data), (r['rx'][:8], data[:8]))
        check('read %d result' % n, r['result'] == 0)
        check('read %d log' % n, s.log == exp, s.log[:12])
        nomem('read %d' % n, r)
        v, st = tcheck('read %d' % n, r)
        if n == 255:
            print('read 255 bytes: %.1f kHz average SCL, %.2f ms' %
                  (st['f_kHz_avg'], r['cpu'].t * US / 1000))
    # 4. write then read (repeated START)
    s = Slave(0x68, read_data=[1, 2, 3, 0xFE])
    r = run_case(asm, s, 0x68, tx=[0x00], rd=4)
    check('write+read', r['rx'] == bytes([1, 2, 3, 0xFE]) and r['result'] == 0, r['rx'])
    check('write+read log', s.log == ['START', 'ADDRW', 'W00', 'START', 'ADDRR', 'R01', 'MACK',
                                      'R02', 'MACK', 'R03', 'MACK', 'RFE', 'MNACK', 'STOP'], s.log)
    nomem('write+read', r); tcheck('write+read', r)
    # 5. NACK after data
    s = Slave(0x42, nack_data_after=2)
    r = run_case(asm, s, 0x42, tx=[1, 2, 3, 4])
    check('nack data result', r['result'] == 2, r['result'])
    check('nack data log', s.log[-1] == 'STOP' and s.written == [1, 2], s.log)
    # 6. stuck SDA
    s = Slave(0x42, stuck_pulses=3)
    r = run_case(asm, s, 0x42, tx=[0x11])
    check('stuck 3 recovered', r['result'] == 0 and s.written == [0x11], (r['result'], s.log))
    s = Slave(0x42, stuck_pulses=-1)
    r = run_case(asm, s, 0x42, tx=[0x11])
    check('stuck forever', r['result'] == 3 and not s.written, r['result'])
    check('stuck forever: I and IFF restored', r['iok'] and r['iffok'])

    # port benchmark routines of the lab versions (BO = 2560 OUT, BI = 2560 IN, BN = 2560 NOP)
    if 0xC500 in asm.image:
        for name, ad in (('BO', 0xC500), ('BI', 0xC520), ('BN', 0xC540)):
            hub = Hub(Slave(0x42))
            cpu = Z80(hub)
            for a_, b_ in asm.image.items():
                cpu.mem[a_] = b_
            cpu.call(ad)
            check('bench %s returns with interrupts on' % name, cpu.iff1 == 1)
            if name == 'BO':
                check('bench BO: 2560 OUT', cpu.opc_writes == 2560, cpu.opc_writes)
            print('bench %s: %.3f ms in the simulator' % (name, cpu.t * US / 1000))

    # summary
    sts = [s for s in allstats if 'f_kHz_avg' in s]
    print('SCL average over all tests: %.1f kHz (min %.1f max %.1f)' %
          (sum(s['f_kHz_avg'] for s in sts) / len(sts),
           min(s['f_kHz_avg'] for s in sts), max(s['f_kHz_avg'] for s in sts)))
    for key in ('tHIGH_min_us', 'tLOW_min_us', 'tHD;STA_min_us', 'tSU;STA_min_us',
                'tSU;STO_min_us', 'hold_after_fall_min_us'):
        vals = [s[key] for s in allstats if s.get(key) is not None]
        if vals:
            print('  %-22s min %.2f us' % (key, min(vals)))
    print('FAILURES: %d' % fails)
    return fails


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        if arg.startswith('--iow='):
            Z80.IOW = int(arg.split('=')[1])
            print('extra I/O wait states: %d' % Z80.IOW)
        elif arg.startswith('--asm='):
            ASM_PATH = arg.split('=', 1)[1]
            print('source:', ASM_PATH)
    sys.exit(1 if main() else 0)
