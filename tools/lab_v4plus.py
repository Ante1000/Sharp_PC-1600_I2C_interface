"""Versions V4 to V7 of the speed-lab drivers (called by make_lab.py).

V4: write block in the page code (no CALL per byte, ACK tested in A, byte counter in E, no memory counter)
V5: V4 + read block in the page code (eight clocks, store, ACK/NACK by jumps, no CALL/RET per byte)
V6: V5 with the clocks written as OUT (C),r (C = 18H, D = 80H, B = SDA state = high address byte, E = byte)
V7: V6 with I = B (HV = 1, LV = 0): the state change needs fewer instructions
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


def sh_stub(v, k):
    if v == 7:
        return 'TL%d:    XOR A\n        LD B,A\n        LD I,A\n        JP SL%dC\n' % (k, k)
    if v == 6:
        return 'TL%d:    LD B,0\n        LD A,LV\n        LD I,A\n        JP SL%dC\n' % (k, k)
    return 'TL%d:    LD A,LV\n        LD I,A\n        JP SL%dC\n' % (k, k)


def sl_stub(v, k):
    if v == 7:
        return 'TH%d:    LD A,1\n        LD B,A\n        LD I,A\n        JP SH%dC\n' % (k, k)
    if v == 6:
        return 'TH%d:    LD B,1\n        LD A,HV\n        LD I,A\n        JP SH%dC\n' % (k, k)
    return 'TH%d:    LD A,HV\n        LD I,A\n        JP SH%dC\n' % (k, k)


def clock_h(v):
    return ('        OUT (C),D\n        OUT (C),B\n' if v >= 6 else
            '        LD A,S_H1\n        OUT (OPC),A\n        LD A,S_L1\n        OUT (OPC),A\n')


def clock_l(v):
    return ('        OUT (C),D\n        OUT (C),B\n' if v >= 6 else
            '        LD A,S_H0\n        OUT (OPC),A\n        LD A,S_L0\n        OUT (OPC),A\n')


def bit(v):
    return 'E' if v >= 6 else 'C'


def pages(v):
    s = []
    nop = ''
    s.append('        ORG 0C100h\nWH:     LD A,S_H1\n        OUT (OPC),A\n        IN A,(PBP)\n        LD D,A\n'
             '        LD A,S_L1\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C120h\nRH:     JP RH2\n')
    s.append('        ORG 0C140h\n')
    for k in range(7, -1, -1):
        s.append('SH%d:    BIT %d,%s\n        JP Z,TL%d\nSH%dC:\n' % (k, k, bit(v), k, k) + clock_h(v))
    s.append('        JP ACKB\n')
    for k in range(7, -1, -1):
        s.append(sh_stub(v, k))
    s.append('        ORG 0C1F5h\nSTH:    LD A,S_H1\n        OUT (OPC),A\n        NOP\n        NOP\n        NOP\n'
             '        LD A,LV\n        LD I,A\n')
    s.append('        ORG 0C200h\nSTT:    NOP\n        NOP\n        LD A,S_L0\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C210h\nWL:     LD A,S_H0\n        OUT (OPC),A\n        LD A,S_L0\n        OUT (OPC),A\n        RET\n')
    s.append('        ORG 0C220h\n')
    for k in range(7, -1, -1):
        lab = 'SL:' if k == 7 else ''
        s.append('%-8sBIT %d,%s\n        JP NZ,TH%d\nSL%dC:\n' % (lab, k, bit(v), k, k) + clock_l(v))
    if v == 7:
        s.append('        LD A,1\n        LD B,A\n        LD I,A\n        JP ACKB\n')
    elif v == 6:
        s.append('        LD B,1\n        LD A,HV\n        LD I,A\n        JP ACKB\n')
    else:
        s.append('        LD A,HV\n        LD I,A\n        JP ACKB\n')
    for k in range(7, -1, -1):
        s.append(sl_stub(v, k))
    if v >= 5:                         # ACK clock of the read block, SDA low
        if v == 7:
            back = '        LD A,1\n        LD B,A\n        LD I,A\n'
        elif v == 6:
            back = '        LD B,1\n        LD A,HV\n        LD I,A\n'
        else:
            back = '        LD A,HV\n        LD I,A\n'
        s.append('ACKL:\n' + (clock_l(v)) + back + '        JP RDB1\n')
    s.append('        ORG 0C2F5h\nSTL:    LD A,S_H0\n        OUT (OPC),A\n        NOP\n        NOP\n        NOP\n'
             '        LD A,HV\n        LD I,A\n')
    s.append('        ORG 0C300h\nSTP2:   NOP\n        NOP\n        NOP\n        LD A,S_L1\n        OUT (OPC),A\n        RET\n')
    # ---- H2 page: receive, ACK of the send block
    s.append('        ORG 0C310h\n')
    if v >= 6:
        rx_bit = '        OUT (C),D\n        LD A,B\n        IN A,(PBP)\n        OUT (C),B\n        RRA\n        RRA\n        RRA\n        RL E\n'
    else:
        rx_bit = ('        LD A,S_H1\n        OUT (OPC),A\n        IN A,(PBP)\n        RRA\n        RRA\n        RRA\n'
                  '        LD A,S_L1\n        OUT (OPC),A\n        RL E\n')
    if v == 4:
        s.append('RH2:\n' + rx_bit * 8 + '        RET\n')
    else:
        s.append('RH2:\nRDB1:\n' + rx_bit * 8)
        s.append('        LD (HL),E\n        INC HL\n')
        if v >= 6:
            s.append('        LD A,(IR)\n        CP L\n        JP Z,LASTB\n')
            s.append('        XOR A\n        LD B,A\n        LD I,A\n        JP ACKL\n' if v == 7 else
                     '        LD B,0\n        LD A,LV\n        LD I,A\n        JP ACKL\n')
            s.append('LASTB:  OUT (C),D\n        OUT (C),B\n        RET\n')
        else:
            s.append('        DEC D\n        JP Z,LASTB\n        LD A,LV\n        LD I,A\n        JP ACKL\n')
            s.append('LASTB:  LD A,S_H1\n        OUT (OPC),A\n        LD A,S_L1\n        OUT (OPC),A\n        RET\n')
    # ACK of the send block (E = bytes left in V4/V5; L compared with IW in V6/V7)
    if v >= 6:
        s.append('ACKB:   OUT (C),D\n        LD A,B\n        IN A,(PBP)\n        BIT 2,A\n        JP NZ,NAKB\n'
                 '        OUT (C),B\n        LD A,(IW)\n        CP L\n        JP Z,DONEB\n        LD E,(HL)\n'
                 '        INC HL\n        JP SH7\n'
                 'NAKB:   OUT (C),B\n        LD D,4\n        RET\nDONEB:  LD D,0\n        RET\n')
    else:
        s.append('ACKB:   LD A,S_H1\n        OUT (OPC),A\n        IN A,(PBP)\n        BIT 2,A\n        JP NZ,NAKB\n'
                 '        LD A,S_L1\n        OUT (OPC),A\n        DEC E\n        JP Z,DONEB\n        LD C,(HL)\n'
                 '        INC HL\n        JP SH7\n'
                 'NAKB:   LD A,S_L1\n        OUT (OPC),A\n        LD D,4\n        RET\nDONEB:  LD D,0\n        RET\n')
    if v >= 5:
        # read block entry (in the main code area, so it is a stub there)
        pass
    return ''.join(s)


def main(v, main_v10):
    m = main_v10
    # write block
    assert MAIN_WRITE_OLD in m
    m = m.replace(MAIN_WRITE_OLD, '        CALL WRBLK\n        BIT 2,D\n        JP NZ,E2\n')
    if v >= 5:
        a = m.index(MAIN_READ_OLD_START)
        b = m.index(MAIN_READ_OLD_END) + len(MAIN_READ_OLD_END)
        m = m[:a] + '        CALL RDB\n' + m[b:]
    # stubs at the end of the main code
    a = m.index('SENDB:')
    m = m[:a]
    m += 'START:  LD A,HV\n        LD I,A\n        JP STH\nSTOP:   LD A,LV\n        LD I,A\n        JP STL\n'
    if v >= 6:
        m += ('SENDB:  LD E,C\n        LD A,(IW)\n        LD L,A\n        LD H,TXH\n        LD BC,0018h\n        LD D,80h\n'
              '        LD A,LV\n        LD I,A\n        JP SL\n')
        m += ('WRBLK:  LD HL,TX\n        LD E,(HL)\n        INC HL\n        LD BC,0118h\n        LD D,80h\n'
              '        LD A,HV\n        LD I,A\n        JP SH7\n')
        m += ('RDB:    LD HL,RX\n        LD BC,0118h\n        LD D,80h\n        LD A,HV\n        LD I,A\n        JP RDB1\n')
    else:
        m += 'SENDB:  LD A,LV\n        LD I,A\n        LD E,1\n        JP SL\n'
        m += ('WRBLK:  LD E,A\n        LD HL,TX\n        LD C,(HL)\n        INC HL\n        LD A,HV\n        LD I,A\n        JP SH7\n')
        if v >= 5:
            m += ('RDB:    LD A,(IR)\n        LD D,A\n        LD HL,RX\n        LD A,HV\n        LD I,A\n        JP RDB1\n')
        else:
            m += 'RECVB:  LD A,HV\n        LD I,A\n        LD B,8\n        JP RH\n'
    return m
