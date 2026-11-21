; =====================================================================
; I2C master v1.0 for the Sharp PC-1600 - runs on the main CPU (Z80, SC-7852)
;
; Pins of the 60-pin system bus connector:
;   SCL      = pin 29 (CMTOUT = SDO of the SC-7852)   OUT (18H),A bit 7   (through a diode)
;   SDA read = pin 27 (CMTIN  = PB2 of the SC-7852)   IN A,(1FH) bit 2    (through 470 ohm)
;   SDA pull = pin 31 (A8, address bus bit 8)         (through a diode)
;
; THE TRICK: PB2 is an input only, and the SC-7852 has no second static output
; pin, so SDA is driven by the ADDRESS BUS. The Z80 drives A8 all the time:
; during an opcode fetch (T1-T2) it shows bit 0 of the high byte of the PC, and
; during the refresh (T3-T4) it shows bit 0 of the I register. If both are the
; same, A8 is a static level. So the SDA level is encoded in the PAGE the code
; runs in AND in the I register:
;       page with A8 = 1 and I odd  -> SDA released (the diode blocks)
;       page with A8 = 0 and I even -> SDA pulled low through the diode
; While the code runs in such a page, A8 is clean. SDA may only be disturbed
; (A8 chops) while SCL is low; START and STOP need one clean edge while SCL is
; high, so they cross a page boundary: LD I,A is the last instruction of the
; page and the next instruction is the first of the next page.
;
; Rules for code that runs while SCL is high (windows):
;   - only registers, IN/OUT and jumps inside the page, NO memory access
;     (no stack, no buffers), because that would put another address on A8;
;   - the A register has bit 0 = the SDA level during OUT/IN (OUT (n),A puts A
;     on the address lines A15-A8 during the I/O cycle).
; The code changes the I register and must be called with interrupts off.
;
; Memory (Z80 addresses; reserve it with NEW "S0:",&1000):
;   C100-C1FF  page H1 (A8 = 1): bit loops with SDA = 1, START (first half)
;   C200-C2FF  page L1 (A8 = 0): bit loops with SDA = 0, START (second half),
;                                STOP (first half)
;   C300-C3FF  page H2 (A8 = 1): STOP (second half)
;   C400-C5FA  main code (entry C400)
;   C5FB       CNT   byte counter
;   C5FC       IA    device address (7 bits)
;   C5FD       IW    number of bytes to write from TX (0-255)
;   C5FE       IR    number of bytes to read into RX (0-255)
;   C5FF       IS    result
;   C600-C6FF  RX    bytes read
;   C700-C7FF  TX    bytes to write
;
; Call (BASIC):  POKE &C5FC, D, W, R : CALL &C400, E
;   W > 0 (or W = 0 and R = 0): START, address+write, TX[0..W-1]
;   R > 0:  (repeated) START, address+read, R bytes into RX (ACK all, NACK last)
;   then STOP.   Result E (also in &C5FF): 0 OK, 1 no ACK after the address,
;   2 no ACK after a data byte, 3 SDA stuck low (nothing sent).
; Registers used: AF, BC, DE, HL, I (restored). Interrupts are restored.
; =====================================================================

HV      EQU 0C1h        ; I for the pages with A8 = 1 (SDA released)
LV      EQU 0C2h        ; I for the pages with A8 = 0 (SDA low)
OPC     EQU 18h         ; port: bit 7 -> SDO (pin 29, SCL), bit 6 -> buzzer (keep 0)
DDB     EQU 1Dh         ; port B direction (bit 2 = PB2 must be an input)
PBP     EQU 1Fh         ; port B data (bit 2 = SDA read back)

S_H1    EQU 81h         ; SCL = 1, A register bit 0 = 1 (A8 = 1)
S_L1    EQU 01h         ; SCL = 0, A8 = 1
S_H0    EQU 80h         ; SCL = 1, A8 = 0
S_L0    EQU 00h         ; SCL = 0, A8 = 0

RX      EQU 0C600h
TX      EQU 0C700h
CNT     EQU 0C5FBh
IA      EQU 0C5FCh
IW      EQU 0C5FDh
IR      EQU 0C5FEh
IS      EQU 0C5FFh

; ---------------------------------------------------------------------
; page H1 (A8 = 1, I = HV): SDA released
; ---------------------------------------------------------------------
        ORG 0C100h
SH:     RLC C                   ; next data bit -> carry
        JP NC,SH_L              ; a 0 bit: SDA must go low
SH_CLK: LD A,S_H1
        OUT (OPC),A             ; SCL = 1
        NOP
        LD A,S_L1
        OUT (OPC),A             ; SCL = 0
        DJNZ SH                 ; 8 bits
WH:     LD A,S_H1               ; one clock with SDA released (ACK bit read,
        OUT (OPC),A             ; NACK sent, bus recovery); CALL entry too
        NOP
        IN A,(PBP)              ; SDA as seen on the bus, bit 2
        LD D,A
        LD A,S_L1
        OUT (OPC),A
        RET
SH_L:   LD A,LV                 ; SCL is low: A8 may chop
        LD I,A
        JP SL_CLK

RH:     LD A,S_H1               ; read one bit (8 times), SDA released
        OUT (OPC),A
        NOP
        IN A,(PBP)
        LD D,A
        LD A,S_L1
        OUT (OPC),A
        LD A,D
        RRA                     ; bit 2 -> carry after three shifts
        RRA
        RRA
        RL E                    ; carry -> E, MSB first
        DJNZ RH
        RET

        ORG 0C1F5h              ; the last 11 bytes of the page: START
STH:    LD A,S_H1
        OUT (OPC),A             ; SCL = 1 (SDA is 1)
        NOP
        NOP
        NOP
        LD A,LV
        LD I,A                  ; last instruction of the page: the next one
                                ; (C200) is fetched with A8 = 0: SDA falls

; ---------------------------------------------------------------------
; page L1 (A8 = 0, I = LV): SDA pulled low
; ---------------------------------------------------------------------
        ORG 0C200h
STT:    NOP                     ; START hold time
        NOP
        LD A,S_L0
        OUT (OPC),A             ; SCL = 0
        RET                     ; back to the caller of START

SL:     RLC C
        JP C,SL_H               ; a 1 bit: SDA must go high
SL_CLK: LD A,S_H0
        OUT (OPC),A             ; SCL = 1
        NOP
        LD A,S_L0
        OUT (OPC),A             ; SCL = 0
        DJNZ SL
        LD A,HV                 ; SDA released for the ACK bit
        LD I,A
        JP WH
SL_H:   LD A,HV
        LD I,A
        JP SH_CLK

WL:     LD A,S_H0               ; one clock with SDA low (ACK sent)
        OUT (OPC),A
        NOP
        LD A,S_L0
        OUT (OPC),A
        RET

        ORG 0C2F5h              ; the last 11 bytes of the page: STOP
STL:    LD A,S_H0
        OUT (OPC),A             ; SCL = 1 (SDA is 0)
        NOP
        NOP
        NOP
        LD A,HV
        LD I,A                  ; the next instruction (C300) has A8 = 1: SDA rises

; ---------------------------------------------------------------------
; page H2 (A8 = 1, I = HV)
; ---------------------------------------------------------------------
        ORG 0C300h
STP2:   NOP                     ; bus free time
        NOP
        NOP
        LD A,S_L1
        OUT (OPC),A             ; SCL = 0, SDA released
        RET                     ; back to the caller of STOP

; ---------------------------------------------------------------------
; main code: A8 may chop here (SCL is always low)
; ---------------------------------------------------------------------
        ORG 0C400h
IC:     LD A,S_L1
        OUT (OPC),A             ; SCL low at once: from here on A8 may chop
        LD A,I
        PUSH AF                 ; I and IFF2 (P/V flag)
        DI
        IN A,(DDB)
        AND 0FBh
        OUT (DDB),A             ; PB2 = input
        XOR A
        LD (IS),A
        CALL BUSCHK
        JP C,E3
        LD A,(IW)
        OR A
        JR NZ,DOWR
        LD A,(IR)
        OR A
        JR NZ,DORD              ; W = 0, R > 0: read at once
DOWR:   CALL START
        LD A,(IA)
        ADD A,A
        LD C,A                  ; address, write bit = 0
        CALL SENDB
        BIT 2,D
        JP NZ,E1                ; no ACK
        LD A,(IW)
        OR A
        JR Z,AFTW
        LD (CNT),A
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
AFTW:   LD A,(IR)
        OR A
        JR Z,DOSTOP
DORD:   CALL START              ; (repeated) START
        LD A,(IA)
        ADD A,A
        INC A
        LD C,A                  ; address, read bit = 1
        CALL SENDB
        BIT 2,D
        JP NZ,E1
        LD A,(IR)
        LD (CNT),A
        LD HL,RX
RLP:    CALL RECVB
        LD (HL),E
        INC HL
        LD A,(CNT)
        DEC A
        LD (CNT),A
        JR Z,RLAST
        LD A,LV
        LD I,A
        CALL WL                 ; ACK
        JR RLP
RLAST:  LD A,HV
        LD I,A
        CALL WH                 ; NACK after the last byte
DOSTOP: CALL STOP
EXIT:   POP AF
        LD I,A                  ; I restored (flags are not changed)
        JP PO,EX2               ; P/V = IFF2: interrupts were off
        EI
EX2:    LD A,(IS)
        LD E,A
        LD D,0
        SCF                     ; CALL IC,E returns the result in E
        RET
E1:     LD A,1
        JR ERR
E2:     LD A,2
ERR:    LD (IS),A
        CALL STOP
        JR EXIT
E3:     LD A,3
        LD (IS),A
        JR EXIT

BUSCHK: LD A,HV                 ; up to 10 clocks until SDA is high
        LD I,A
        LD B,10
BC1:    CALL WH
        BIT 2,D
        JR NZ,BCOK
        DJNZ BC1
        SCF                     ; SDA stuck low
        RET
BCOK:   OR A
        RET

START:  LD A,HV
        LD I,A
        JP STH
STOP:   LD A,LV
        LD I,A
        JP STL
SENDB:  LD A,LV                 ; send the byte in C, then read the ACK bit into D
        LD I,A
        LD B,8
        JP SL
RECVB:  LD A,HV                 ; read a byte into E
        LD I,A
        LD B,8
        JP RH
