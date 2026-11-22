; =====================================================================
; I2C master LH v1.0 for the Sharp PC-1600 - runs on the LH-5803 (XCALL)
;
; This is the PC-1500 driver i2c_v1.4.asm of
; https://github.com/Ante1000/Sharp_PC-1500_I2C_interface adapted to the PC-1600.
; The LH-5803 of the PC-1600 is the CPU of the PC-1500 (LH5801 code, 1.3 MHz) and sees the same
; port block at &F000 of the ME1 space. Pins of the 60-pin connector:
;   SCL      = pin 29 (CMTOUT = SDO), port C &F008 bit 7 (PC7)       (through a diode)
;   SDA read = pin 27 (CMTIN  = PB2), OPB &F00F bit 2                (through 470 ohm)
;   SDA pull = pin 15 (PU), the PU flip-flop of the LH-5803: SPU = released, RPU = low
;                                                                    (through a diode)
; Changes against v1.4:
;   - PB2 cannot drive the line on the PC-1600, so SDA is driven by PU: SDA = 0 is RPU, SDA = 1
;     is SPU (1 byte, 4 cycles) instead of the open drain emulated with DDB/OPB (17 cycles).
;     There is no OPB latch to clear and DDB bit 2 only has to be an input (once, at the start).
;   - X = &F00F all the time (the read of SDA).
;   - No SIE at the end: the interrupts of the LH-5803 are left as they are after RIE.
;   - PU is left high (SDA released) when the routine returns; PU is also a memory bank signal of
;     the PC-1600 slots: use it without memory cards in the slots until it is checked.
; Memory (Z80 addresses = LH addresses + &8000; reserve with NEW "S0:",&1000):
;   LH &4A00 (Z80 &CA00)  RX buffer      LH &4B00 (Z80 &CB00)  TX buffer
;   LH &4C00 (Z80 &CC00)  code, IC = &4C00 (XCALL)   &4CFC IA  &4CFD IW  &4CFE IR  &4CFF IS
; Call (BASIC):  POKE &CCFC, D, W, R : XCALL &4C00, E       (buffers: POKE/PEEK &CB00, &CA00)
; Results as for the Z80 driver: 0 OK, 1 no ACK after the address, 2 no ACK after a data
; byte, 3 SDA stuck low.
; Symbols filled in by the assembler (-D): IP=&4C TP=&4B RP=&4A BM=4 DB=&FB.
; The original comment block (explanation of the loops) follows in the PC-1500 source.
; =====================================================================
        RIE                     ; no interrupts
        LDI  XH,&F0
        LDI  XL,&0F             ; X = &F00F (OPB: read SDA), unchanged below
        LDI  YH,&F0
        LDI  YL,&08             ; Y = &F008 (port C: SCL = PC7)
        ANI  #(&F00D),DB        ; DDB: PB2 is an input (it only reads SDA)
        SPU                     ; SDA = 1 (released)
        ORI  #(Y),&80           ; SCL = 1
        LDI  UL,9               ; SDA = 0: up to 10 SCL pulses
BUSY:   BII  #(X),BM            ; SDA = 1 -> bus free
        BZR+ FREE
        ANI  #(Y),&7F           ; SCL pulse: a device that holds
        ORI  #(Y),&80           ; SDA sends its next bit
        LOP  UL,BUSY
        LDI  A,3                ; SDA still 0: result 3, no START/STOP
        BCH+ EXIT
FREE:   LDI  UL,0               ; UL = 0 (= W when reading without a write)
        LDA  (IP,&FD)           ; W
        STA  (IP,WCMP+1)        ; W into the instruction CPI UL,W in SEND
        BZR+ WR
        LDA  (IP,&FE)           ; R
        BZR+ RD                 ; W = 0, R > 0: read at once
WR:     LDI  UH,TP              ; U = TX
        REC                     ; C = 0: address for writing
        SJP  ADDR               ; address, then W bytes from TX
        BCS+ WEND               ; C = 1: everything acknowledged
        LDA  UL                 ; no ACK: UL = 0 -> after the address
        BZS+ NAKA
        BCH+ NAKD
WEND:   LDA  (IP,&FE)           ; R
        BZS+ OK
RD:     STA  (IP,RCMP+1)        ; A = R (from FREE or WEND) into CPI UL,R
        SEC                     ; C = 1: address for reading (UL = W, so SEND
        SJP  ADDR               ; ends after the address alone)
        BCR+ NAKA
        DCS  (X)                ; time for the device: SCL low for about 77 us
        REC                     ; C = 0: the receive loop needs this
        LDI  UH,RP
        LDI  UL,0               ; U = RX
RBYTE:  LDI  A,1                ; sentinel: leaves into C after 8 bits
RBIT:   ORI  #(Y),&80           ; SCL = 1
        BII  #(X),BM            ; read SDA
        BZS+ R0
        SEC                     ; bit 1 (C = 0 in the loop, so bit 0 needs no REC)
R0:     ROL                     ; A = A*2 + bit
        ANI  #(Y),&7F           ; SCL = 0
        BCR- RBIT               ; C = 1: the sentinel left, byte complete
        SIN  U                  ; store, U++
RCMP:   CPI  UL,0               ; UL - R (R written in RD): C = 1 for the last one
        BCS+ R9                 ; last one: NACK (SDA = 1)
        RPU                     ; ACK: SDA = 0
R9:     ORI  #(Y),&80           ; 9th SCL pulse (ACK or NACK)
        ANI  #(Y),&7F           ; (ORI/ANI do not change C)
        BCS+ OK
        SPU                     ; release SDA; C = 0
        BCH- RBYTE
OK:     LDI  A,0
        BCH+ STOP
NAKA:   LDI  A,1
        BCH+ STOP
NAKD:   LDI  A,2
STOP:   SJP  SDA0               ; SDA = 0 while SCL = 0
        ORI  #(Y),&80           ; SCL = 1
        SPU                     ; SDA 0 -> 1 while SCL = 1: STOP
EXIT:   STA  (IP,&FF)           ; IS = result
        STA  XL
        LDI  XH,0               ; X = result ...
        SEC                     ; ... C=1: BASIC copies X into E of XCALL IC,E
        RTN
;
; START: SDA 1 -> 0 while SCL = 1, then SCL = 0 (A and C unchanged).
; SDA0 (entry from STOP while SCL = 0): SDA = 0, and the second SCL = 0 changes nothing.
START:  SPU                     ; SDA = 1
        ORI  #(Y),&80           ; SCL = 1
SDA0:   RPU                     ; SDA 1 -> 0 (START)
        ANI  #(Y),&7F           ; SCL = 0
        RTN
;
; ADDR: START (or repeated START), then the byte D*2+C and further bytes from TX.
; After START SDA = 0, so sending starts in state L.
ADDR:   SJP  START
        LDA  (IP,&FC)           ; D
        ROL                     ; D*2 + C (0 write, 1 read)
        SEC
        ROL                     ; C = bit 7, sentinel 1 -> bit 0
        BCH+ LDEC
;
; SEND: sends the byte in A, then further bytes from TX (LIN U), until UL = W.
; Result: C = 1 everything acknowledged, C = 0 no ACK (UL tells after which).
; Two states: H (SDA = 1) and L (SDA = 0); only a bit that differs from the
; previous one changes SDA. The end of a byte (sentinel: A = 0, Z flag after
; SHL/ROL) only counts after a 1 bit - after a 0 bit (C = 0) it cannot be the sentinel.
H0:     RPU                     ; H, bit 0: SDA = 0 -> state L
LC:     ORI  #(Y),&80           ; SCL pulse
        ANI  #(Y),&7F
        SHL                     ; C = next bit
LDEC:   BCR- LC                 ; L, bit 0: SDA unchanged
        BZS+ SACKL              ; C = 1 and Z = 1: sentinel, end of the byte
        SPU                     ; L, bit 1: SDA = 1 -> state H
HC:     ORI  #(Y),&80           ; SCL pulse
        ANI  #(Y),&7F
        SHL
HDEC:   BCR- H0                 ; H, bit 0
        BZR- HC                 ; H, bit 1: SDA unchanged
        BCH+ SACKH              ; sentinel in state H: SDA already released
SACKL:  SPU                     ; release SDA: the device sends the ACK
SACKH:  ORI  #(Y),&80           ; 9th SCL pulse
        BII  #(X),BM            ; ACK = 0
        BZR+ SNAK
        ANI  #(Y),&7F           ; SCL = 0
WCMP:   CPI  UL,0               ; W bytes sent? (W written in FREE; equal: C = 1)
        BZS+ SDONE
        LIN  U                  ; A = byte, U++
        SEC
        ROL                     ; C = bit 7, sentinel 1 -> bit 0
        BCH- HDEC               ; after the ACK SDA is released: state H
SNAK:   ANI  #(Y),&7F           ; SCL = 0
        REC                     ; C = 0: no ACK
SDONE:  RTN
