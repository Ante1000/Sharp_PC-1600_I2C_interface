; =====================================================================
; I2C LH diagnostic v1.0 for the Sharp PC-1600 (LH-5803, XCALL &4D00)
; Checks the three lines of the LH driver (SCL pin 29, SDA read pin 27, SDA drive pin 15 = PU)
; step by step and stores the results in a table at LH &4DF0 (Z80 &CDF0); the BASIC program
; pc1600_i2c_lh_diag-v1.0.txt reads the table and prints numbered findings.
; Table: +0 DDB bit 2 still set (1 = bad)     +1 RPU pulled SDA low (1 = yes), +2 loops left
;        +3 SPU released SDA (1 = yes), +4 loops left   +5 SDA high right after SPU + SCL=1 (as the driver)
;        +6 SDA high after 10 SCL pulses      +7 START: SDA low after RPU with SCL = 1
;        +8 STOP: SDA high after SPU with SCL = 1, +9 loops left
; "loops left" = UL after the wait loop (255 = at once, small = slow, flag 0 = timeout).
; One wait loop pass is about 33 cycles (25 us).
; =====================================================================
        RIE
        LDI  XH,&F0
        LDI  XL,&0F             ; X = &F00F (read SDA, bit 2)
        LDI  YH,&F0
        LDI  YL,&08             ; Y = &F008 (port C, SCL = bit 7)
        ANI  #(&F00D),&FB       ; DDB bit 2 = input
        LDI  A,0
        BII  #(&F00D),4
        BZS+ DD
        LDI  A,1
DD:     STA  (&4DF0)            ; +0
;
; 1: RPU, SDA must go low
        RPU
        LDI  UL,255
W1:     BII  #(X),4
        BZS+ G1
        LOP  UL,W1
        LDI  A,0
        STA  (&4DF1)
        BCH+ S2
G1:     LDA  UL
        STA  (&4DF2)
        LDI  A,1
        STA  (&4DF1)
;
; 2: SPU, SDA must go high
S2:     SPU
        LDI  UL,255
W2:     BII  #(X),4
        BZR+ G2
        LOP  UL,W2
        LDI  A,0
        STA  (&4DF3)
        BCH+ S3
G2:     LDA  UL
        STA  (&4DF4)
        LDI  A,1
        STA  (&4DF3)
;
; 3: as the driver starts: low for a while, then SPU, SCL = 1, one read at once
S3:     RPU
        LDI  UL,255
D3:     LOP  UL,D3              ; about 1.5 ms: SDA is low
        SPU
        ORI  #(Y),&80           ; SCL = 1
        LDI  UL,9
        BII  #(X),4
        BZR+ H3
        LDI  A,0
        BCH+ P3
H3:     LDI  A,1
P3:     STA  (&4DF5)
;
; 4: wait until SDA is high, then 10 SCL pulses with SDA released, read SDA
        LDI  UL,255
W4:     BII  #(X),4
        BZR+ P4
        LOP  UL,W4
P4:     LDI  UL,9
L4:     ANI  #(Y),&7F
        ORI  #(Y),&80
        LOP  UL,L4
        LDI  A,0
        BII  #(X),4
        BZS+ S5
        LDI  A,1
S5:     STA  (&4DF6)
;
; 5: START: SCL = 1, RPU: SDA must be low
        RPU
        LDI  UL,255
W5:     BII  #(X),4
        BZS+ G5
        LOP  UL,W5
        LDI  A,0
        BCH+ P5
G5:     LDI  A,1
P5:     STA  (&4DF7)
        ANI  #(Y),&7F           ; SCL = 0
;
; 6: STOP: SCL = 1, SPU: SDA must go high
        ORI  #(Y),&80
        SPU
        LDI  UL,255
W6:     BII  #(X),4
        BZR+ G6
        LOP  UL,W6
        LDI  A,0
        STA  (&4DF8)
        BCH+ EX
G6:     LDA  UL
        STA  (&4DF9)
        LDI  A,1
        STA  (&4DF8)
EX:     ANI  #(Y),&7F           ; SCL = 0
        LDI  A,0
        STA  XL
        LDI  XH,0
        SEC
        RTN
