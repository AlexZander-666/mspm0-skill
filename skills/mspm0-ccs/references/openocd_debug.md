# OpenOCD / GDB Debug

Use this reference when probing, flashing, or debugging MSPM0 hardware through OpenOCD. This backend is separate from CCS Debug Server Scripting (`ccs-dss`).

Before selecting this backend for an unspecified probe, run:

```powershell
python scripts\detect_probe.py
python scripts\check_syscfg.py <project-dir> --probe
```

Use OpenOCD only when the detected probe and interface configuration are compatible.

## Verified Scope

The packaged helper was verified with:

- MSPM0G3507 hardware
- CMSIS-DAP / DAPLink probe
- an MSPM0-capable OpenOCD build containing `target/ti_mspm0.cfg`
- `interface/cmsis-dap.cfg`
- `arm-none-eabi-gdb`
- a TI Arm Clang-generated CCS `.out` ELF file

The helper can also use `.elf`, `.axf`, `.hex`, and `.bin` outputs. A raw `.bin` requires `--base-address`.

OpenOCD MSPM0 support commonly requires a TI MSPM0-capable build or TI extension branch. Do not assume an unrelated mainline OpenOCD installation can access MSPM0 correctly.

## Commands

From the installed skill directory:

```powershell
python scripts\openocd_debug.py <project-dir> probe
python scripts\openocd_debug.py <project-dir> flash
python scripts\openocd_debug.py <project-dir> registers
python scripts\openocd_debug.py <project-dir> run-to-symbol --symbol main
```

Other available actions:

```powershell
python scripts\openocd_debug.py <project-dir> halt
python scripts\openocd_debug.py <project-dir> run
python scripts\openocd_debug.py <project-dir> reset
python scripts\openocd_debug.py <project-dir> reset --halt
```

The default config and fallback speeds are:

```text
interface/cmsis-dap.cfg
target/ti_mspm0.cfg
24000,1000,500 kHz
```

Override them only when the connected probe, target support package, or project requires a different choice:

```powershell
python scripts\openocd_debug.py <project-dir> --interface <interface.cfg> --target <target.cfg> --speeds 24000,1000,500 probe
```

## Flash Behavior

`flash` auto-detects a compatible program output under the project directory, then performs:

```text
init
reset halt
flash write_image erase <program>
reset halt
verify_image <program>
reset run
shutdown
```

Use `--program <path>` when several outputs exist and the automatic choice is ambiguous. Use `--no-verify` only when the user explicitly accepts losing verification.

## Connection Failures And Retries

The helper separates probe and transport failures from firmware failures. Its default retry order is `24000`, `1000`, then `500` kHz.

- `unable to find a matching CMSIS-DAP device`: probe discovery failure. Check the USB or wireless DAPLink connection.
- `CMSIS-DAP command mismatch` or `CMD_CONNECT failed`: likely link corruption, wireless interruption, or another debug process holding the probe.
- target halt, SWD ACK, or DAP access failures: retry after reconnecting and lowering speed; if repeated, check wiring and ask whether the target needs manual unlock.
- verify failure: retry with a stable connection and lower speed before changing commands.

Do not run parallel OpenOCD operations against one probe. Flash, register reads, and GDB sessions can contend with each other.

## Locked Or Protected Targets

The helper intentionally does not perform automatic unlock, mass erase, or factory reset operations.

If it reports `target_locked_or_protected`, stop retries and ask the user to run their known manual unlock or recovery procedure. This avoids destructive recovery when a transient wireless failure merely resembles a target-access problem.

## Debug Safety

`probe`, `registers`, `halt`, `reset --halt`, and `run-to-symbol` can halt the CPU. Before using them on motors, power electronics, or other real-time control systems:

1. Warn the user that debug actions may pause control loops.
2. Put actuators into a safe state when possible.
3. Avoid leaving the target halted unless the user requests it.

Use `ccs_dss_debug.py` instead when the user explicitly wants the CCS / CCS Theia / UniFlash Debug Server Scripting path and has a matching `targetConfigs/*.ccxml`.
