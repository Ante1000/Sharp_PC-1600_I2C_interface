"""Versions V8 to V10 of the speed-lab drivers (called by make_lab.py). Based on V5 (the fastest
version on the real PC-1600 in the first runs) and V7.

V8:  V5 with the clock values held in registers: LD A,B / LD A,D (4 T) instead of LD A,n (7 T).
     write block: B = S_H1, D = S_L1, E = byte counter, C = byte; read block: B = S_H1, C = S_L1
V9:  V8 with I = 0 / 1 (as V7): after a clock A is 01h or 00h, so the state change is INC A / DEC A
     (4 T) instead of LD A,n (7 T)
V10: V7 (OUT (C),r clocks) with cheaper state changes (INC B / DEC B instead of LD A,1 / LD B,A)
"""

MAIN_WRITE_OLD = '''        LD (CNT),A
        LD HL,TX
WLP:    LD C,(HL)
        INC HL
        CALL SENDB
        BIT 2,D
        JP NZ,E2
        LD A,(CNT)
        DEC A
        LD (CNT),A
        JR NZ,WLP
'''
MAIN_READ_OLD_START = '        LD A,(IR)\n        LD (CNT),A\n        LD HL,RX\nRLP:'
MAIN_READ_OLD_END = '        CALL WH                 ; NACK after the last byte\n'


def pagesA(v):
    """V8, V9 (OUT (n),A clocks with registers)"""
    fast = v >= 9
    # state changes: V9 uses A = 01h after a high-page clock (DEC A -> 00h = LV) and A = 00h after a
    # low-page clock (INC A -> 01h = HV)
    to_low = '        DEC A\n        LD I,A\n' if fast else '        LD A,LV\n        LD I,A\n'
    to_high = '        INC A\n        LD I,A\n' if fast else '        LD A,HV\n        LD I,A\n'
    s = []
    s.append('        ORG 0C100h\nWH:     LD A,S_H1\n        OUT (OPC),A\n        IN A,(PBP)\n        LD D,A\n'
             '        LD A,S_L1\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C120h\nRH:     JP RH2\n')
    s.append('        ORG 0C140h\n')
    for k in range(7, -1, -1):
        s.append('SH%d:    BIT %d,C\n        JP Z,TL%d\nSH%dC:\n' % (k, k, k, k) +
                 '        LD A,B\n        OUT (OPC),A\n        LD A,D\n        OUT (OPC),A\n')
    s.append('        JP ACKB\n')
    for k in range(7, -1, -1):
        s.append('TL%d:\n' % k + to_low + '        JP SL%dC\n' % k)
    s.append('        ORG 0C1F5h\nSTH:    LD A,S_H1\n        OUT (OPC),A\n        NOP\n        NOP\n        NOP\n'
             '        LD A,LV\n        LD I,A\n')
    s.append('        ORG 0C200h\nSTT:    NOP\n        NOP\n        LD A,S_L0\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C210h\nWL:     LD A,S_H0\n        OUT (OPC),A\n        LD A,S_L0\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C220h\n')
    for k in range(7, -1, -1):
        lab = 'SL:' if k == 7 else ''
        s.append('%-8sBIT %d,C\n        JP NZ,TH%d\nSL%dC:\n' % (lab, k, k, k) +
                 '        LD A,S_H0\n        OUT (OPC),A\n        XOR A\n        OUT (OPC),A\n')
    s.append(to_high + '        JP ACKB\n')
    for k in range(7, -1, -1):
        s.append('TH%d:\n' % k + to_high + '        JP SH%dC\n' % k)
    s.append('ACKL:\n        LD A,S_H0\n        OUT (OPC),A\n        XOR A\n        OUT (OPC),A\n' + to_high + '        JP RDB1\n')
    s.append('        ORG 0C2F5h\nSTL:    LD A,S_H0\n        OUT (OPC),A\n        NOP\n        NOP\n        NOP\n'
             '        LD A,HV\n        LD I,A\n')
    s.append('        ORG 0C300h\nSTP2:   NOP\n        NOP\n        NOP\n        LD A,S_L1\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C310h\n')
    rx_bit = ('        LD A,B\n        OUT (OPC),A\n        IN A,(PBP)\n        RRA\n        RRA\n        RRA\n'
              '        LD A,C\n        OUT (OPC),A\n        RL E\n')
    s.append('RH2:\nRDB1:\n' + rx_bit * 8)
    s.append('        LD (HL),E\n        INC HL\n        DEC D\n        JP Z,LASTB\n' + to_low.replace('        DEC A\n', '        DEC A\n') +
             '        JP ACKL\n')
    s.append('LASTB:  LD A,B\n        OUT (OPC),A\n        LD A,C\n        OUT (OPC),A\n        RET\n')
    s.append('ACKB:   LD A,B\n        OUT (OPC),A\n        IN A,(PBP)\n        BIT 2,A\n        JP NZ,NAKB\n'
             '        LD A,D\n        OUT (OPC),A\n        DEC E\n        JP Z,DONEB\n        LD C,(HL)\n'
             '        INC HL\n        JP SH7\n'
             'NAKB:   LD A,D\n        OUT (OPC),A\n        LD D,4\n        RET\nDONEB:  LD D,0\n        RET\n')
    return ''.join(s)


def pagesB(v):
    """V10: V7 (OUT (C),r) with INC B / DEC B state changes"""
    s = []
    s.append('        ORG 0C100h\nWH:     LD A,S_H1\n        OUT (OPC),A\n        IN A,(PBP)\n        LD D,A\n'
             '        LD A,S_L1\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C120h\nRH:     JP RH2\n')
    s.append('        ORG 0C140h\n')
    for k in range(7, -1, -1):
        s.append('SH%d:    BIT %d,E\n        JP Z,TL%d\nSH%dC:\n        OUT (C),D\n        OUT (C),B\n' % (k, k, k, k))
    s.append('        JP ACKB\n')
    for k in range(7, -1, -1):
        s.append('TL%d:    DEC B\n        LD A,B\n        LD I,A\n        JP SL%dC\n' % (k, k))
    s.append('        ORG 0C1F5h\nSTH:    LD A,S_H1\n        OUT (OPC),A\n        NOP\n        NOP\n        NOP\n'
             '        LD A,LV\n        LD I,A\n')
    s.append('        ORG 0C200h\nSTT:    NOP\n        NOP\n        LD A,S_L0\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C210h\nWL:     LD A,S_H0\n        OUT (OPC),A\n        LD A,S_L0\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C220h\n')
    for k in range(7, -1, -1):
        lab = 'SL:' if k == 7 else ''
        s.append('%-8sBIT %d,E\n        JP NZ,TH%d\nSL%dC:\n        OUT (C),D\n        OUT (C),B\n' % (lab, k, k, k))
    s.append('        INC B\n        LD A,B\n        LD I,A\n        JP ACKB\n')
    for k in range(7, -1, -1):
        s.append('TH%d:    INC B\n        LD A,B\n        LD I,A\n        JP SH%dC\n' % (k, k))
    s.append('ACKL:\n        OUT (C),D\n        OUT (C),B\n        INC B\n        LD A,B\n        LD I,A\n        JP RDB1\n')
    s.append('        ORG 0C2F5h\nSTL:    LD A,S_H0\n        OUT (OPC),A\n        NOP\n        NOP\n        NOP\n'
             '        LD A,HV\n        LD I,A\n')
    s.append('        ORG 0C300h\nSTP2:   NOP\n        NOP\n        NOP\n        LD A,S_L1\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C310h\n')
    rx_bit = '        OUT (C),D\n        LD A,B\n        IN A,(PBP)\n        OUT (C),B\n        RRA\n        RRA\n        RRA\n        RL E\n'
    s.append('RH2:\nRDB1:\n' + rx_bit * 8)
    s.append('        LD (HL),E\n        INC HL\n        LD A,(IR)\n        CP L\n        JP Z,LASTB\n'
             '        DEC B\n        LD A,B\n        LD I,A\n        JP ACKL\n')
    s.append('LASTB:  OUT (C),D\n        OUT (C),B\n        RET\n')
    s.append('ACKB:   OUT (C),D\n        LD A,B\n        IN A,(PBP)\n        BIT 2,A\n        JP NZ,NAKB\n'
             '        OUT (C),B\n        LD A,(IW)\n        CP L\n        JP Z,DONEB\n        LD E,(HL)\n'
             '        INC HL\n        JP SH7\n'
             'NAKB:   OUT (C),B\n        LD D,4\n        RET\nDONEB:  LD D,0\n        RET\n')
    return ''.join(s)


def pages(v):
    return pagesB(v) if v == 10 else pagesA(v)


def main(v, main_v10):
    m = main_v10
    assert MAIN_WRITE_OLD in m
    m = m.replace(MAIN_WRITE_OLD, '        CALL WRBLK\n        BIT 2,D\n        JP NZ,E2\n')
    a = m.index(MAIN_READ_OLD_START)
    b = m.index(MAIN_READ_OLD_END) + len(MAIN_READ_OLD_END)
    m = m[:a] + '        CALL RDB\n' + m[b:]
    a = m.index('SENDB:')
    m = m[:a]
    m = m.replace('START:  LD A,HV\n        LD I,A\n        JP STH\nSTOP:   LD A,LV\n        LD I,A\n        JP STL\n', '')
    m += 'START:  LD A,HV\n        LD I,A\n        JP STH\nSTOP:   LD A,LV\n        LD I,A\n        JP STL\n'
    if v == 10:
        m += ('SENDB:  LD E,C\n        LD A,(IW)\n        LD L,A\n        LD H,TXH\n        LD BC,0018h\n        LD D,80h\n'
              '        LD A,LV\n        LD I,A\n        JP SL\n')
        m += ('WRBLK:  LD HL,TX\n        LD E,(HL)\n        INC HL\n        LD BC,0118h\n        LD D,80h\n'
              '        LD A,HV\n        LD I,A\n        JP SH7\n')
        m += ('RDB:    LD HL,RX\n        LD BC,0118h\n        LD D,80h\n        LD A,HV\n        LD I,A\n        JP RDB1\n')
    else:
        m += 'SENDB:  LD B,S_H1\n        LD D,S_L1\n        LD A,LV\n        LD I,A\n        LD E,1\n        JP SL\n'
        m += ('WRBLK:  LD E,A\n        LD HL,TX\n        LD C,(HL)\n        INC HL\n        LD B,S_H1\n        LD D,S_L1\n'
              '        LD A,HV\n        LD I,A\n        JP SH7\n')
        m += ('RDB:    LD A,(IR)\n        LD D,A\n        LD HL,RX\n        LD BC,S_H1*256+S_L1\n'
              '        LD A,HV\n        LD I,A\n        JP RDB1\n')
    return m
