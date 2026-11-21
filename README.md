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
4. The code stays in memory when you erase the program with `NEW` in PRO mode, as long as you
   keep the reservation (do not repeat `NEW "S0:"` with a smaller size).

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
driver first (`NEW "S0:",&1000`, installer, then `NEW` in PRO mode is not needed: type the
BMP280 program after the installer has run, or load it into the memory above the machine-language
area), then `RUN`. It shows

```
Temperature = 25.08 C
Pressure = 1006.53 hPa
I2C approx. 34 kHz
```

The speed is measured with 255-byte reads from the sensor for 3 seconds with the clock of the
computer (`TIME`) as the time base, counting the SCL clocks (2322 per read). It is an
approximate **effective** value, a few percent below the real SCL frequency because it includes the
BASIC statements between the reads. It is measured at the start, and again when you press **S**
during the measurement loop (any other key stops the program).

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
| `Basic/pc1600_i2c_installer-v1.0.txt` | BASIC installer, scanner and test |
| `Basic/pc1600_bmp280-v1.0.txt` | thermometer and barometer with a BMP280 (address &77) that also shows the approximate I2C speed, see below |
| `tools/` | mini assembler, simulator with the tests, installer generator |
| `docs/design_notes.md` | analysis: pins, registers, alternatives that were considered |

## Sources

- Sharp PC-1600 Technical Reference (60-pin connector p. 278, SC-7852 pins and I/O map, I/O port
  controller registers 18H-1FH, memory banks) and the Service Manual (circuit diagrams):
  [sharp-pc-1600.de](https://sharp-pc-1600.de/).
- [Sharp PC-1500 I2C interface](https://github.com/Ante1000/Sharp_PC-1500_I2C_interface) and
  [Software UART](https://github.com/Ante1000/Sharp_PC-1500_Software_UART) (the same author).

## Author

Alex F4VTS. The driver, the simulator and the notes were written with help from Claude Code.
