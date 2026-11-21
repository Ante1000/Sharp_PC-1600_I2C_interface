# Design notes: I2C on the PC-1600

How the pins were chosen and what was tried or rejected. Facts come from the Sharp PC-1600
Technical Reference (TR) and Service Manual (SM) at [sharp-pc-1600.de](https://sharp-pc-1600.de/),
and from measurements on a real PC-1600 by the author.

## 1. The 60-pin connector is a Z80 bus

TR section 10.3 (and SM, CN-9): pins 1-8 A7-A0, 9 INT1, 10 M1, 11 VCC, 12 NC, 13 RSTE, 14 PT,
15 PU, 16 PVOUT, 17-24 D7-D0, 25 INH, 26 IORQ, **27 CMTIN**, 28 WAIT, **29 CMTOUT**, 30 IRQ,
31-38 A8-A15, 39 VGG, 41 VCC, 43-44 FG, 45-46 VBAT, 47 VP, 49 MREQ, 50 BFO, 51 ΦOS, 52-54 GND,
56 DMEO, 57 WR, 58 ELH, 59 IOE, 60 RD. (On the PC-1500 pins 9 and 10 are PB0 and PC7.)

The FPC circuit diagram in the SM shows that CMTOUT (CN2-46) is connected straight to pin 76 of the
SC-7852 (SDO) and CMTIN (CN2-48) to pin 71 (PB2). PU (CN2-60) comes from the LH-5803, PT and PVOUT
from the SC-7852.

## 2. Z80-side ports (TR 7.9, 7.1.1)

The SC-7852 contains an LH-5810/5811 compatible port block at Z80 I/O 18H-1FH:
OPC 18H, MSK 1AH, IF 1BH, DDA 1CH, DDB 1DH, OPA 1EH, OPB 1FH.

- OPC bit 7 -> SDO (pin 29, CMTOUT). OPC bit 6 -> PC6 (buzzer, inverted).
- PB2 is documented as an input with an internal pull-up (cassette read signal), and it is
  mixed into the buzzer signal together with PC6, PC7 and SDO.
- MSK (1AH) reads back the levels of CL1, SO1, PB7 and IRQ in its upper four bits; IRQ is pin 30
  (internal pull-down). This could read SCL back for clock stretching (not tried).

## 3. What was measured

See the table in the README. In short: pin 29 is a static output, pin 27 a readable input, and
**PB2 cannot be driven** (DDB bit 2 = 1, OPB bit 2 = 0: still 5 V). So a third line is needed
for the SDA drive, and it must be a static output.

## 4. Candidates for the third line

| Candidate | Result |
|---|---|
| **A8 (pin 31) by code page and I register** | **chosen**. Static level 0 V / 5 V measured; the refresh shows I (mismatch gives 375 kHz chopping). |
| PT, PU, PVOUT in Z80 mode | rejected: they are the bank bits of I/O port 31H and follow the region the CPU is accessing (TR 7.2.1), so they are not static. |
| PU (pin 15) with `SPU`/`RPU` on the LH-5803 | works (measured), but only the LH-5803 can set it; kept as a fallback, see below. |
| Sub-CPU (RSTE) | rejected: commands only every 1/64 s. |
| INT1 (pin 9), IRQ (pin 30), WAIT (pin 28) | inputs only. |
| 74HC74 clocked by /WR (pin 57) with D0 (pin 24) | would work (one chip), but random memory writes change it; needs gating. |
| other bus lines | not static (data bus floats between cycles, address lines change every cycle). |

### The address bus as a port

Fetch (T1-T2): A15-A8 = PC high byte. Refresh (T3-T4): A15-A8 = I register. Memory data cycles:
the data address. I/O cycles: A or B register (`OUT (n),A`, `OUT (C),r`). If the code runs in one
page and I has the same bit 0, A8 is static. The consequences, all handled by the driver:

1. SDA may only chop while SCL is low (bit changes, entry, exit).
2. While SCL is high there must be no memory data access and the A register must have the right bit 0.
3. START/STOP: one clean edge by letting `LD I,A` be the last instruction of the page. With two or
   more instructions between `LD I,A` and the page change the refresh and fetch phases disagree
   and the edge bounces (the simulator detects this).
4. If SCL is high when the routine is entered, the first instructions can produce START/STOP
   pairs (BASIC's I and the page of the code disagree): SDO should idle low.

### The LH-5803 variant (not built)

`XCALL` runs LH5801 code on the LH-5803 (the PC-1500 CPU, 1.3 MHz) with the Z80 halted.
Measured: `XPOKE# &F008,&80` / `0` moves pin 29 (PC7 = SDO), `XPEEK#(&F00F)` bit 2 follows pin 27
(after `OUT &1D,0`: an earlier DDB bit 2 = 1 made the read return the latch), and `SPU` (E1) / `RPU`
(E3) move pin 15 (PU). So the PC-1500 driver could run with SCL on pin 29, SDA read on pin 27
and SDA drive on pin 15 (`RPU` = low, `SPU` = released, 4 cycles instead of 17). It would
be roughly as fast as the PC-1500 version; the Z80 driver is about twice as fast.

## 5. Open points for the hardware

- Does the real bus stay clean (scope on SDA with a device): START, STOP, bit changes?
- Idle level of pin 29 in BASIC; does the buzzer click during a transfer?
- Is a 3.3 V high level enough for pin 27?
- Reading SCL back through IRQ (pin 30, MSK bit) for clock stretching.
