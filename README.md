# I2C interface for the Sharp PC-1600 (Z80)

**I2C master v1.0 for the PC-1600** by Alex F4VTS

A machine-language routine for the **main CPU of the PC-1600 (Z80, SC-7852)** that turns the
computer into an **I2C bus master** with no dedicated interface and no modification of the
computer. It uses three pins of the 60-pin system bus connector: **pin 29** (SCL), **pin 27**
(SDA read) and **pin 31** (SDA drive). It is the PC-1600 counterpart of the
[I2C interface for the Sharp PC-1500(A)](https://github.com/Ante1000/Sharp_PC-1500_I2C_interface),
and the call interface is the same.

> **Status (please read).** The driver has been written and tested **only in a simulator**
> (Z80 with the bus cycles of every instruction, the I2C wires and simulated I2C devices, see
> [Simulation](#simulation)). It has **not yet been run on a real PC-1600**. The ideas it
> depends on were measured on a real PC-1600 (see [Measurements](#measurements-on-a-real-pc-1600)),
> but the whole driver on a real bus is the next step. Please check the wiring carefully and
> report your results.

## Why this is not a port of the PC-1500 code

On the PC-1500 the 60-pin connector has the port pins PC7 (pin 10) and PB2 (pin 27) and PB0
(pin 9). The PC-1600 connector is a **Z80 system bus**: pin 10 is `M1`, pin 9 is `INT1`, and
the only port lines left are `CMTIN` (pin 27) and `CMTOUT` (pin 29):

| Pin | Signal | Inside the SC-7852 | Use here |
|---|---|---|---|
| 29 | CMTOUT | SDO, output only, port 18H bit 7 | **SCL** (through a diode) |
| 27 | CMTIN | PB2, **input only**, port 1FH bit 2 | **SDA read** (through 470 Ω) |
| 31 | A8 | address bus bit 8 | **SDA drive** (through a diode) |
| 52-54 | GND | | GND |
| 11, 41 | VCC | | (5 V, small loads only) |

PB2 cannot drive the line (measured: with DDB bit 2 = 1 and OPB bit 2 = 0 the pin stays at 5 V),
and the SC-7852 has no second static output on the connector. So SDA is driven by the
**address bus**, see [How it works](#how-it-works).

## Connection

```
PC-1600 (60-pin)                                          I2C device / module
                    Schottky diode (BAT43, BAT85, 1N5817)
pin 29 CMTOUT ──────────────|<|─────────────┬──────────────────────  SCL
               (cathode/stripe toward pin 29)│
                                            4.7k (optional)
                                             │
                                            VCC
                    Schottky diode
pin 31 A8     ──────────────|<|─────────────┬──────────────────────  SDA
               (cathode/stripe toward pin 31)│
                                            4.7k (optional)
                                             │
pin 27 CMTIN  ───────────[ 470 ohm ]─────────┘            (to the SDA node)  VCC
pin 52-54 GND ───────────────────────────────────────────────────────────── GND
```

- **VCC** is the supply of the I2C device (3.3 V or 5 V) with its own supply and a common GND.
  The pull-up resistors (4.7-10 kΩ) are not needed if the module already has them.
- **The diodes** make the PC-1600 outputs open-drain: a pin can only pull the line low, the
  pull-up makes the high level, and a 3.3 V bus never sees the 5 V of the PC-1600. Schottky
  diodes are best (low level about 0.3-0.5 V); a 1N4148 works with 5 V devices.
- **The 470 Ω resistor on pin 27** only limits the current, it is a read-only input. The PC-1600
  inputs probably need a high level well above 2.4 V (the SC-7852 is a 5 V CMOS part), so a
  3.3 V bus may be too low for pin 27: use a 5 V pull-up or a level converter if the scanner
  does not find a 3.3 V device.
- **Remove the CE-1600P** (and any cassette cable): it uses the same pins (CMTIN/CMTOUT).
- **Idle level of pin 29:** measure it with the computer in BASIC. It should be **low** (see
  [Limitations](#limitations)).
- While a BASIC program runs, the address line A8 toggles all the time and pulls SDA low through
  the diode. With SCL idle low this is harmless (no clock pulses, so no device reads data),
  but for the first tests a **jumper or switch in the pin 31 wire** is a good idea.

## Installation

1. Switch the PC-1600 on in the PRO or RUN mode with a free memory and type
   `NEW "S0:",&1000` [ENTER] (this reserves the machine-language area &C0C5 to &CFFF and erases
   the BASIC program in memory).
2. Type in `Basic/pc1600_i2c_installer-v1.0.txt` (or load it from a file) and `RUN` it. It
   POKEs 369 bytes into &C100 to &C4EA and prints `I2C Z80 V1.0 INSTALLED`.
3. `RUN 500` is the **scanner** (tries every address 8 to 119 and lists the devices that
   answer, address in hex). `RUN 700` is a **test**: it asks for an address, the bytes to write
   and the number of bytes to read.
4. To load another program (for example the BMP280 program) afterwards, type
   `NEW "S0:",&1000` again with the **same size** (a plain `NEW` would release the
   machine-language area). That erases the BASIC program only; the programs that use the driver
   check that the code is still there (`PEEK &C400` = 62) and say `I2C NOT INSTALLED` if it is
   not: run the installer again then. After a reset or a power failure check the same way.

## Use in your programs

```
POKE &C5FC, D, W, R : CALL &C400, E
```

Put the W bytes to write into **TX = &C700**, set the device address `D` (7 bits, 0-127), `W` and
`R`, and call the routine. The bytes read are in **RX = &C600**.

- If W > 0 (or W = 0 and R = 0): START, address + write bit, then TX+0 to TX+W-1.
- If R > 0: (repeated) START, address + read bit, then R bytes into RX (ACK for all but the last).
- At the end: STOP. With W = 0 and R = 0 only the address is sent: a presence test.

| Result `E` (also in &C5FF) | Meaning |
|---|---|
| 0 | OK |
| 1 | no ACK after the address (no device, or it is busy) |
| 2 | no ACK after a data byte |
| 3 | SDA stays low: the bus is blocked; nothing was sent (up to 10 clock pulses are tried first) |

| Address | Contents |
|---|---|
| &C100-&C3FF | the three code pages (see below) |
| &C400-&C4EA | main code (entry &C400) |
| &C5FB | CNT (byte counter) |
| &C5FC | IA: device address |
| &C5FD | IW: number of bytes to write |
| &C5FE | IR: number of bytes to read |
| &C5FF | IS: result |
| &C600-&C6FF | RX: bytes read |
| &C700-&C7FF | TX: bytes to write |

Example, DS3231 real-time clock (address &68): set 23:59:30 and read it back (BCD as hex):

```
10 POKE &C700, 0, &30, &59, &23 : POKE &C5FC, &68, 4, 0 : CALL &C400, E
20 POKE &C700, 0 : POKE &C5FC, &68, 1, 3 : CALL &C400, E
30 S = PEEK &C600 : M = PEEK &C601 : H = PEEK &C602
40 PRINT E; " "; HEX$(H); ":"; HEX$(M); ":"; HEX$(S)
```

(`HEX$` accepts only a simple variable or a number, so the bytes are copied to variables first.)

The routine disables the interrupts while it runs (the 64 Hz key scan is not served; a 255-byte
transfer takes about 60 ms) and restores the interrupts and the I register at the end. The
registers AF, BC, DE, HL are changed. `CALL &C400, E` returns the result in `E` because the
routine returns with the carry flag set and DE = result.

## How it works

PB2 is an input and the SC-7852 has no other static output on the connector, but the Z80
drives its address bus all the time. During an opcode fetch (T1-T2) the line A8 shows bit 0 of
the high byte of the program counter, and during the refresh (T3-T4) it shows bit 0 of the
**I register**. If both agree, A8 is a static level, so:

- code running in a page with A8 = 1 (&C1xx, &C3xx) and `I` odd releases SDA (the diode blocks),
- code running in a page with A8 = 0 (&C2xx) and `I` even pulls SDA low through the diode.

The **state of SDA is the page the code runs in**, like the two-state send loop of the PC-1500
driver (v1.1 and later). The listing `asm/i2c_z80_v1.0.asm` explains the rules:

- **Bit loops** (`SH` in page &C1xx, `SL` in page &C2xx): a bit equal to the previous one just
  clocks SCL; a different bit does `LD I,A` and jumps to the other page *while SCL is low*, so a
  chop of A8 at that moment is harmless.
- **While SCL is high** the code uses only registers, `IN`/`OUT` and jumps inside the page: no
  stack, no buffers, because another address on A8 would be a glitch on SDA. During `OUT (n),A`
  and `IN A,(n)` the high address byte is the A register, so its bit 0 always equals the SDA level.
- **START and STOP** need exactly one clean SDA edge while SCL is high. They cross a page
  boundary: `LD I,A` is the last instruction of the page and the next instruction (first of the
  next page) is fetched with the new A8 level (START: &C1FF to &C200; STOP: &C2FF to &C300).
- **SCL** comes from SDO (port 18H bit 7), a clean static output; bit 6 of the port (buzzer) is
  always 0.
- **SDA read** is PB2 (port 1FH bit 2); DDB bit 2 is cleared (input) at the start.

The code is 369 bytes in four pieces (57 + 58 + 19 + 235; the PC-1500 v1.4 has 252 bytes), because it
needs two copies of the bit loop and the page alignment.

## Speed

From the simulator (3.58 MHz Z80, no allowance for a real machine being a few percent slower):

| Transfer | SCL average | Time | Bytes/s |
|---|---|---|---|
| write 255 bytes | 37.1 kHz | 62 ms | about 4100 |
| read 255 bytes | 34.4 kHz | 67 ms | about 3800 |

For comparison, the PC-1500 driver (LH5801, 1.3 MHz) reaches 17.5 kHz and 1884 bytes/s, so this
driver should be about twice as fast. The shortest clock phases are tHIGH 6.2 µs and tLOW 7.3 µs,
START/STOP times 7-8 µs: all comfortably inside the standard mode (100 kHz) minimum times.

## Example: BMP280 thermometer and barometer

`Basic/pc1600_bmp280-v1.0.txt` is the PC-1600 version of the
[PC-1500 BMP280 program](https://github.com/Ante1000/Sharp_PC-1500_I2C_interface/blob/main/BMP280_thermo_baro_Example.md)
(same module and settings: address &77 with SDO at VDDIO, forced mode, oversampling 1 to 16 and
IIR filter chosen at the start, datasheet compensation in floating point). Install the I2C
driver first (`NEW "S0:",&1000`, installer), then type `NEW "S0:",&1000` again, load the
BMP280 program and then `RUN`. It shows

```
Temperature = 25.08 C
Pressure = 1006.53 hPa
I2C approx. 34 kHz
```

The speed is measured with 255-byte reads from the sensor for 4 seconds with the clock of the
computer (`TIME`, read after every 4 reads to keep its overhead small) as the time base, counting the SCL clocks (2322 per read); the time of one 255-byte read in ms is printed too. It is an
approximate **effective** value, a few percent below the real SCL frequency because it includes the
BASIC statements between the reads. It is measured at the start, and again when you press **S**
during the measurement loop (any other key stops the program).

## Loading from tape

**With a CE-1600P or CE-152 (MODE 0, PC-1600 tape format):** play `wav/pc1600_i2c_installer-v1.0_mode0_CE-1600P.wav` and
`LOAD "CAS:I2CZ80"` (after `NEW "S0:",&1000`), `RUN`; later `NEW "S0:",&1000` again and
`LOAD "CAS:BMP280"` with `wav/pc1600_bmp280-v1.0_mode0_CE-1600P.wav` (about 2 to 3 minutes each).
These recordings are ASCII BASIC files made by `tools/pc1600_cas_bas2wav.py` (the tool of the
[Software UART repository](https://github.com/Ante1000/Sharp_PC-1600_Software_UART/tree/main/tools));
like the tool, they were only checked with its decoder, **not on a real PC-1600**.

**With only a CE-150 (MODE 1, PC-1500 tape format):**

Without a CE-1600P the programs can be loaded through a CE-150 exactly as the Saver/Loader of
[SerComet](https://github.com/Ante1000/SerComet_transfer_tool_for_pockets/tree/main/Saver-Loader/PC-1600):
switch the PC-1600 to **MODE 1**, play `wav/pc1600_i2c_installer-v1.0_mode1_CE-150.wav` into the CE-150 and `CLOAD`
it, switch back to **MODE 0** and `RUN` it (the program stays in memory; its machine code is for the
Z80 of MODE 0). Reserve the machine-language area first with `NEW "S0:",&1000`; after the
installer has run, repeat `NEW "S0:",&1000` in MODE 0, switch to MODE 1, `CLOAD` the BMP280 program
(`wav/pc1600_bmp280-v1.0_mode1_CE-150.wav`) and go back to MODE 0.

The recordings are made with `tools/pc1600_bas2wav.py program.txt out.wav NAME`: it tokenizes the
program with the PC-1600 token table (the tokenizer of SerComet, ported to Python) and writes the tape
format of the PC-1500 (8 s leader tone, 44100 Hz, about 3 to 4 minutes). The tokenizer was checked by
reproducing the program bytes of the recording `sl1600_mode1_CE-150.wav` of SerComet exactly, and each
recording is decoded back and compared with the text (`--check`). **The recordings have not yet
been played into a real PC-1600.**

## LH-5803 variant (for comparison)

`asm/i2c_lh_v1.0.asm` is the PC-1500 driver (v1.4 of the
[PC-1500 repository](https://github.com/Ante1000/Sharp_PC-1500_I2C_interface)) adapted to the PC-1600 and run
on the **LH-5803** with `XCALL` (the CPU of the PC-1500, 1.3 MHz, the Z80 is stopped meanwhile). It
keeps **pins 29 (SCL) and 27 (SDA read)** and drives SDA with **pin 15 (PU)** instead of pin 31 (A8):
`RPU` pulls the line low through the diode, `SPU` releases it. So **move the SDA diode from pin 31 to pin 15**
(cathode toward the pin). The rest of the wiring is the same.

| | Z80 driver | LH-5803 driver |
|---|---|---|
| SCL | pin 29, OUT (18H) bit 7 | pin 29, port C &F008 bit 7 |
| SDA read | pin 27, IN (1FH) bit 2 | pin 27, OPB &F00F bit 2 |
| SDA drive | pin 31 (A8) by code page and I | pin 15 (PU): `SPU` / `RPU`, 4 cycles |
| code | 369 bytes | 217 bytes (the PC-1500 v1.4 has 252) |
| call | `POKE &C5FC,D,W,R : CALL &C400,E` | `POKE &CCFC,D,W,R : XCALL &4C00,E` |
| buffers | TX &C700, RX &C600 | TX &CB00, RX &CA00 (Z80 addresses of the same RAM) |
| speed | about 35 kHz (simulator) | about 20 kHz (estimate from the cycle counts, **not simulated**) |

Both can be installed at the same time (their memory does not overlap): installer
`Basic/pc1600_i2c_lh_installer-v1.0.txt` (`NEW "S0:",&1000` first), program `Basic/pc1600_bmp280_lh-v1.0.txt`,
which is the Z80 BMP280 program with the addresses and `XCALL` changed (it prints the I2C speed in the
same way, so the two drivers can be compared on the same sensor).
The LH source was assembled with `tools/lh5801asm_mini.py`, which reproduces the listing of the PC-1500 v1.4
byte for byte (`--selftest`); the changes against v1.4 only replace the SDA operations, so the flags that
the branches use are untouched. The variant has **not been simulated or run on a real PC-1600**.
Known unknowns: PU is also a memory bank signal for the slots (PU is left high when the routine returns:
use it without memory cards for now); the interrupts of the LH-5803 are not switched on at the end (no `SIE`).

## Combined programs (driver + BMP280 in one file)

For a quick start there is one BASIC program per driver that contains the machine code (in `DATA`
lines from 4000) and the BMP280 program: `Basic/pc1600_i2c_z80_bmp280-v1.0.txt` (Z80 driver) and
`Basic/pc1600_i2c_lh_bmp280-v1.0.txt` (LH-5803 driver; SDA diode on pin 15). Tape recordings
(MODE 0, CE-1600P): `wav/pc1600_i2c_z80_bmp280-v1.0_mode0_CE-1600P.wav` (tape name `BMPZ80`, about 4.5 minutes) and
`wav/pc1600_i2c_lh_bmp280-v1.0_mode0_CE-1600P.wav` (`BMPLH`, about 4 minutes).

1. `NEW "S0:",&1000` (reserves the machine-language area; without it the code would overwrite the
   BASIC program). On the first run the program shows where it starts and asks `DID YOU TYPE NEW S0 (Y)`:
   answer `Y` only if you did. (An earlier version stopped by itself with the pointer formula of the
   SerComet Saver/Loader, which gave a wrong value on the real machine; the value is now printed.)
2. `LOAD "CAS:BMPZ80"` (or `BMPLH`) and `RUN`.
3. Line 5 installs the driver when it is not in memory (a few seconds), then the BMP280 program starts.
   Later runs find the driver and skip the installation.

The files are made by `tools/make_combined.py` from the assembler sources and the BMP280 programs
(`--check` compares the DATA lines with the assembler output). Like the other programs, **not yet tried on a real PC-1600**.

## LH diagnostic program

`Basic/pc1600_i2c_lh_diag-v1.0.txt` (tape `wav/pc1600_i2c_lh_diag-v1.0_mode0_CE-1600P.wav`, name `DIAGLH`,
source `asm/i2c_lh_diag_v1.0.asm`) checks the three lines of the LH driver step by step and prints numbered
findings. Use it with the SDA diode on **pin 15 only** (pin 31 disconnected), after `NEW "S0:",&1000`:

| Message | Meaning |
|---|---|
| E1 DDB BIT 2 STAYS SET | PB2 stays an output: the read of SDA returns the latch |
| E2 RPU: SDA NOT PULLED LOW | the diode on pin 15 does not pull SDA low (reversed, open, wrong pin) |
| E3 SDA STAYS LOW AFTER SPU | something holds SDA low: a diode left on pin 31, the sensor, no pull-up |
| E4 SDA TOO SLOW | SDA rises, but not within the time the driver waits (needs a delay) |
| E5 SDA LOW AFTER 10 CLK | SDA is low after 10 SCL pulses: SCL does not reach the device or it holds SDA |
| E6 START: SDA NOT LOW | START cannot pull SDA low with SCL high |
| E7 STOP: SDA NOT HIGH | STOP cannot release SDA with SCL high |

The last line gives the SDA rise time in microseconds (counts of about 25 us). `ALL OK` means all steps passed.
Made by `tools/make_diag.py`; assembled with the checked LH assembler, **not tried on a real PC-1600**.

## Driver version 1.1 (the fastest one, recommended)

The speed lab (below) produced a faster Z80 driver, **v1.1** (`asm/i2c_z80_v1.1.asm`, the lab version V10). It has the same interface as v1.0
(`POKE &C5FC,D,W,R : CALL &C400,E`, buffers at &C600 / &C700), so your programs do not change. Measured on the real PC-1600: **about 43 kHz read and 54 kHz write**
(v1.0: about 14 kHz as shown by the BMP280 program, whose meter included the BASIC `CALL` overhead; 32 / 40 kHz with the old lab method). It needs
`NEW0` followed by `NEW "S0:",&800` (a smaller area than v1.0 needs, &1000 also works).

| File | Contents |
|---|---|
| `Basic/pc1600_i2c_installer-v1.1.txt` | installer, scanner (`RUN 500`) and test (`RUN 700`) for v1.1 |
| `Basic/pc1600_bmp280-v1.1.txt` | the BMP280 program for v1.1; its speed meter now uses the routine `REP` of the driver (10 reads per `CALL`) and subtracts the time of an empty `CALL`, so it shows the real SCL speed (takes about 25 s) |
| `Basic/pc1600_i2c_z80_bmp280-v1.1.txt` | both in one file (about 2.4 KB of memory stay free) |

`tools/make_v11.py` builds them (`--check` compares the DATA lines with the assembler). The BMP280 program v1.1 was run on the real machine (255-byte read 50 to 54 ms, 43 to 47 kHz); the v1.0 files stay as they are.

## Z80 speed lab

Five BASIC programs install the Z80 driver and measure how fast it really is, one small optimisation step at a time:

| File | Versions | Measurement | Free memory after `NEW "S0:",&800` |
|---|---|---|---|
| `Basic/pc1600_z80_speedlab-v2.1_V0-V3.txt` | V0, V1, V2, V3 | old (10 s window, 1 transfer per call) | about 2.9 KB |
| `Basic/pc1600_z80_speedlab-v2.2_V4-V5.txt` | V4, V5 | **accurate** | about 2.4 KB |
| `Basic/pc1600_z80_speedlab-v2.2_V6-V7.txt` | V6, V7 | **accurate** | about 2.4 KB |
| `Basic/pc1600_z80_speedlab-v2.2_V8-V9.txt` | V8, V9 | **accurate** | about 2.5 KB |
| `Basic/pc1600_z80_speedlab-v2.2_V10.txt` | V10 | **accurate** | about 4 KB |

Each program verifies every version on the BMP280 (chip ID, a signature of the 24 calibration bytes, a write + read-back of the
config register with three bit patterns) before it times it, and prints `TRY Vn` first, so a version that hangs the machine can be recognised.
The program text is that of the version 1.2 that ran V0 to V3 on the real PC-1600 (decimal `DATA`, the same reader); the only changes are
the range of the `FOR V` loop and a generic "next block" call. One program holds only two to four versions because the DATA of a full
image is large; the first version of each program is stored completely, the next ones as differences.

**Always type `NEW0` first and then `NEW "S0:",&800`, never `NEW0` alone**: with `NEW0` alone no machine-language area is reserved and the
installer overwrites the BASIC program and its variables (hangs, returns to BASIC, errors 10 and 19 in the earlier tests of this lab came from that).
Then `LOAD`/receive the program and `RUN`; answer `Y` to the question.
After a freeze reset the PC-1600 **and switch the BMP280 supply off and on**: the sensor may be left in the middle of a transfer.
(A version 2.0 with hexadecimal DATA and a `START AT V` question froze after the chip ID on the real machine and was dropped.)

**The old file** `Basic/archive/pc1600_z80_speedlab-v1.2.txt` (V0 to V3, ran on the real PC-1600) is kept unchanged.

**Measuring method (v2.2).** The BASIC `CALL` statement itself is slow (80 to 300 ms per call on the real PC-1600), and `TIME` has a resolution of
1 s. The first results (v2.1) were therefore noisy: V4 and V5 have the same write code, but the program measured 52 and 71 kHz. In v2.2 the Z80 routine
`REP` (at &C580) calls the driver K = 20 times in one BASIC `CALL` (one call then takes about one second, the interrupts are left on between the transfers),
each timing lasts 30 s, the empty-call overhead is measured for 20 s and subtracted, and the 1 s granularity of `TIME` is corrected by half a second.
The error should be a few percent. The result line is `Vn OK R <kHz> W <kHz>` (read and write of 255 bytes; the write test sends 255 zero bytes,
which the BMP280 takes as writes of 0 to the reserved register 0) and `READ 255 B = <ms>`. One version takes about 1.5 minutes.

**The steps** (the numbers are the simulator, 3.58 MHz; V0 to V3 were measured on the real PC-1600 earlier):

| Version | What changes | Sim write / read | Real write / read |
|---|---|---|---|
| V0 | the driver v1.0 (a NOP in every clock) | 36.9 / 34.4 kHz | 40 / 32 kHz |
| V1 | no NOPs, shorter receive loop | 38.5 / 38.5 | 40 / 32 |
| V2 | send loop unrolled (`BIT n,C`) | 43.7 / 38.5 | 52 / 32 |
| V3 | receive loop unrolled (8 clocks, no loop) | 43.7 / 43.1 | 52 / 40 |
| V4 | write block in the page code: no `CALL` per byte, ACK tested in `A`, byte counter in `E` | 48.9 / 43.1 | ? |
| V5 | V4 + read block in the page code (ACK/NACK by jumps, no `CALL`/`RET` per byte) | 48.9 / 49.4 | ? |
| V6 | V5 with the clocks as `OUT (C),r` (C = 18H, D = 80H, B = SDA state, E = byte) | 53.7 / 53.4 | ? |
| V7 | V6 with I = B (HV = 1, LV = 0): the state change needs fewer instructions | 55.6 / 54.2 | ? |
| V8 | V5 with the clock values in registers (`LD A,B` / `LD A,D`, 4 T, instead of `LD A,n`, 7 T); `XOR A` for the low value | 52.2 / 53.6 | ? |
| V9 | V8 with I = 0 / 1: after a clock A is already 01h or 00h, so the state change is `INC A` / `DEC A` (4 T) | 53.4 / 54.1 | ? |
| V10 | V7 (`OUT (C),r` clocks) with `INC B` / `DEC B` state changes | 56.3 / 54.5 | ? |

V6 and V7 shorten the SCL high time to 3.35 us (at 3.58 MHz): below the 4 us of the standard mode, but far above the 0.6 us of the fast mode
that the BMP280 and most devices accept. V7 sets the I register to 0 / 1, so the refresh addresses lie in the ROM area (not tried on the machine).
All eight versions pass the whole simulator test set (`python3 tools/z80_i2c_sim.py --asm=asm/i2c_z80_lab_v7.asm`, ...), including NACK after the
address and after data, a stuck SDA, interrupts on or off, and random I.

The sources are `asm/i2c_z80_lab_v0.asm` to `_v7.asm`, generated by `tools/make_lab.py` and `tools/lab_v4plus.py`
(`python3 tools/make_lab.py --check` compares the DATA lines of the three programs with the assembler).
**Results on the real PC-1600** (accurate method v2.2; the BASIC `CALL` takes 310 ms), read / write in kHz and the time of a 255-byte read:

| Version | Read / write | Read 255 B | Model `--real`, read |
|---|---|---|---|
| V4 | 34 / 45 | 65 ms | 63.5 ms |
| V5 | 41 / 45 | 57 ms | 56.0 ms |
| V6 | 43 / 51 | 54 ms | 53.3 ms |
| V7 | 43 / 51 | 54 ms | 52.7 ms |
| V8 | **hangs** (reason not found) | | |
| V9 | not tried (same code family as V8) | | |
| V10 | **43 / 54** | 54 ms | 52.4 ms |

The old noisy numbers (V3 34/34 ... V7 43/35) are obsolete. Analysis:

- **The port lab** (`Basic/pc1600_z80_portlab-v1.0.txt`, run on the real machine) gave: BASIC `CALL` 301 to 306 ms; `NOP` (routine with its loop) 1.87 to 2.06 us;
  `OUT (n),A` 4.078 us; `IN A,(n)` 4.078 us; `OUT (C),r` and `IN r,(C)` 4.664 us, for **all ports 18H to 1FH and for B = 00, 01, 81**.
  So a port read is **not** slower than a write, the port and the high address byte do not matter, and an ideal 3.58 MHz Z80 would need
  1.57 / 3.52 / 3.80 us. (An earlier guess in this file, "IN costs 28 T", was wrong: it only mimicked the real effect.)
- The real machine fits a simple model: **one extra wait state in every opcode fetch (M1) and one in every I/O cycle** (a prefixed instruction has two opcode
  fetches, so it costs 2 T more). The simulator option `--real` (= `--m1w=1 --iow=1`) reproduces the port lab (NOP 1.90, OUT 4.14, OUT (C) 4.70 us) and the speed lab
  within 1 to 4 %:

  | Version | Model read / write | Real read / write |
  |---|---|---|
  | V4 | 63.5 / 49.1 ms | 65 / 51.2 ms |
  | V5 | 56.0 / 49.1 | 57 / 51.2 |
  | V6 | 53.3 / 43.9 | 54 / 45.2 |
  | V7 | 52.7 / 43.2 | 54 / 45.2 |
  | V10 | 52.4 / 43.0 | 54 / 42.7 |

  and the BMP280 program v1.1 shows 50 to 54 ms and 43 to 47 kHz for a 255-byte read (V10 = driver v1.1).
- With this cost model the number of instructions counts as much as the T-states: a read bit of V10 is `OUT (C),D` 15 T, `LD A,B` 5, `IN` 13, `OUT (C),B` 15,
  `RRA` x3 15, `RL E` 10 = 73 T, and a byte adds about 144 T (two state changes of 32 T, `LD (HL),E`, counter, ACK clock). The `OUT (C),r` family is cheaper
  than `OUT (n),A` + `LD A,r` (30 against 36 T per clock) and the data bit test `BIT n,r` + `JP cc` costs 21 T. I found no cheaper replacement for the shift that
  takes the bit from PB2 (3 x `RRA` + `RL E`), for the two state changes of the ACK clock or for the byte counter: **V10 is practically the optimum of this
  design (about 43 kHz read / 54 kHz write on the real PC-1600)**; the remaining ideas save 1 % at best. A further step would need another way to read SDA
  or both lines on the address bus (other wiring), and all code lies in RAM with an opcode wait state, so only a faster memory region would help.
- V8 (V5 with the clock values in registers) froze the machine although it passes the whole simulator test set, also with `--real`. It does the same
  bus accesses as V5 (same values on A15 to A8 in every `OUT`) in a different instruction order, the reason was not found and it was not pursued because the
  `OUT (n),A` family is slower anyway. V9 is built on V8 and was not run.

## Limitations

- **Pin 29 (SDO) should be low when the computer is idle.** If it is high, the first
  instructions of the routine (before it pulls SCL low) put a few START/STOP pairs on the bus
  (the simulator shows one to three). They carry no clock pulses, so devices ignore them, but
  it is not clean. At the end the routine leaves SCL low (OPC = 01H).
- **No clock stretching** (SCL cannot be read back), a single master only, 7-bit addresses.
- **Interrupts are off** during a `CALL`; no other program may change the I register or run
  at the same time.
- **The buzzer:** PB2 and SDO are mixed into the buzzer signal in the SC-7852. The driver never
  changes port bit 6, but the transfer may still click: please report it.
- **A8 toggles on SDA** whenever BASIC runs (see the connection notes): a jumper in the pin 31
  wire is recommended; a MOSFET with its gate on A8 and its source on PU (pin 15, an
  LH-5803 flip-flop output) would be an electronic enable, not needed for tests.
- The addresses are fixed (&C100-&C7FF) and need `NEW "S0:",&1000` or larger.

## Measurements on a real PC-1600

Made by Alex F4VTS before this driver was written (multimeter and oscilloscope):

| Test | Result |
|---|---|
| `OUT &18,&80` / `OUT &18,0` | pin 29 toggles (SCL) |
| `INP(&1F)` with pin 27 open / to GND | 111 / 107 (79 / 75 after `OUT &1D,0`): bit 2 follows the pin (SDA read) |
| `OUT &1D,4 : OUT &1F,0` in a loop | pin 27 stays at 5 V: **PB2 is an input only** |
| Z80 code in &C1xx with I = &C1 | pin 31 (A8) = 5 V, static |
| Z80 code in &C0xx with I = &C0 | pin 31 (A8) = 0 V, static |
| Z80 code in &C0xx with I = &C1 | pin 31 mean 0.7 V, 2 V pulses at 375 kHz: **the refresh puts I on A8** |
| LH-5803 (`XCALL`) `SPU` / `RPU` | pin 15 (PU) = 5 V / 0 V (an alternative SDA drive, see below) |
| LH-5803 `XPOKE# &F008,&80` / `0`, `XPEEK#(&F00F)` | pin 29 toggles, bit 2 follows pin 27 |

The last two rows describe an LH-5803 variant (three lines on pins 29, 27 and 15, running the
PC-1500 code with `SPU`/`RPU` for SDA) that was not built, because the Z80 version is faster.
See [docs/design_notes.md](docs/design_notes.md).

## Simulation

`tools/z80_i2c_sim.py` runs the driver in a Z80 simulator with the bus cycles of every
instruction and the level of A8 in every T-state, the I2C wires, and I2C slaves that check every
START, STOP, byte and ACK, and the standard-mode timing. Any glitch of A8 while SCL is high
shows up as an extra START/STOP. It covers: presence test, writes of 1 to 255 bytes and all byte
values, reads, write + read with a repeated START, NACK after the address and after a data byte,
a device holding SDA low (recovered after 3 pulses, or never), SCL high or low at entry,
interrupts on or off, a DDB with bit 2 set, random I, and extra I/O wait states.
Mutation tests (wrong I, a second instruction after `LD I,A`, a memory access with SCL high)
are all detected.

```
python3 tools/z80_i2c_sim.py            # the tests
python3 tools/z80_i2c_sim.py --iow=1    # with one more wait state in every I/O cycle
python3 tools/z80_i2c_sim.py --asm=asm/i2c_z80_v1.1.asm --real   # wait states of the real machine (M1 +1, I/O +1)
python3 tools/z80asm_mini.py asm/i2c_z80_v1.0.asm -l asm/i2c_z80_v1.0.lst
python3 tools/make_installer.py         # rebuilds the BASIC installer (--check compares it)
```

`tools/z80asm_mini.py` is a small assembler for the instructions the driver uses; the source is
ordinary Z80 syntax and also assembles with z80asm, pasmo or sjasmplus (use `ORG`/`DB`/`EQU`
as written). The simulator is a model made from the Z80 and the SC-7852 documentation; it has not been
compared with the real machine.

## Repository contents

| File | Contents |
|---|---|
| `asm/i2c_z80_v1.0.asm`, `.lst` | Z80 source with the explanation, and the listing with the bytes |
| `asm/i2c_z80_v1.1.asm`, `.lst` | the faster Z80 driver v1.1 (see "Driver version 1.1") |
| `Basic/pc1600_i2c_installer-v1.0.txt` | BASIC installer, scanner and test |
| `Basic/pc1600_z80_portlab-v1.0.txt` | times `NOP`, `OUT`, `IN` on the real machine (port lab) |
| `Basic/pc1600_bmp280-v1.0.txt` | thermometer and barometer with a BMP280 (address &77) that also shows the approximate I2C speed, see below |
| `wav/*_mode0_CE-1600P.wav` | the installer (`I2CZ80`) and the BMP280 program (`BMP280`) as tape recordings in the PC-1600 format (MODE 0, `LOAD "CAS:NAME"`) |
| `wav/*_mode1_CE-150.wav` | the same programs in the PC-1500 / CE-150 format (MODE 1, `CLOAD`) |
| `asm/i2c_lh_v1.0.asm`, `.lst`, `Basic/pc1600_i2c_lh_installer-v1.0.txt`, `Basic/pc1600_bmp280_lh-v1.0.txt` | the LH-5803 variant (PC-1500 driver adapted, `XCALL`), its installer and BMP280 program, for comparison with the Z80 driver, see below |
| `Basic/pc1600_i2c_z80_bmp280-v1.0.txt`, `Basic/pc1600_i2c_lh_bmp280-v1.0.txt` | **combined programs**: the driver installer and the BMP280 program in one BASIC file (Z80 driver / LH-5803 driver), see below |
| `wav/pc1600_i2c_z80_bmp280-v1.0_mode0_CE-1600P.wav`, `wav/pc1600_i2c_lh_bmp280-v1.0_mode0_CE-1600P.wav` | the two combined programs for `LOAD "CAS:BMPZ80"` / `"CAS:BMPLH"` (MODE 0, CE-1600P) |
| `wav/*` | the four programs as tape recordings: `_mode1_CE-150.wav` (PC-1500 format, `CLOAD` in MODE 1) and `_mode0_CE-1600P.wav` (PC-1600 format, `LOAD "CAS:NAME"`) |
| `Basic/pc1600_z80_speedlab-v2.1_V*.txt`, `asm/i2c_z80_lab_v*.asm` | the Z80 **speed lab**: installer, port benchmark, speed ladder V0-V7 in three programs, verified on the BMP280, see below |
| `tools/` | mini assemblers (Z80 and LH5801), simulator with the tests, installer generators, simulator with the tests, installer generator, `pc1600_bas2wav.py` (BASIC text to a MODE 1 / CE-150 recording), `pc1600_cas_bas2wav.py` (to a MODE 0 / CE-1600P recording, from the Software UART repository) |
| `docs/design_notes.md` | analysis: pins, registers, alternatives that were considered |

## Sources

- Sharp PC-1600 Technical Reference (60-pin connector p. 278, SC-7852 pins and I/O map, I/O port
  controller registers 18H-1FH, memory banks) and the Service Manual (circuit diagrams):
  [sharp-pc-1600.de](https://sharp-pc-1600.de/).
- [Sharp PC-1500 I2C interface](https://github.com/Ante1000/Sharp_PC-1500_I2C_interface) and
  [Software UART](https://github.com/Ante1000/Sharp_PC-1500_Software_UART) (the same author).

## Author

Alex F4VTS. The driver, the simulator and the notes were written with help from Claude Code.
