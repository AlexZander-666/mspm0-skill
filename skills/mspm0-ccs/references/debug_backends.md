# Debug Backends

Use this reference when the user asks the agent to flash or debug a connected MSPM0 board. Keep CCS-DSS and OpenOCD/GDB as separate backends.

Before selecting a backend for an unspecified probe, run:

```powershell
python scripts\detect_probe.py
python scripts\check_syscfg.py <project-dir> --probe
```

Probe detection is read-only. Do not flash when multiple probes are connected, detection is unknown, or the physical probe conflicts with project configuration until the user confirms the intended backend.

Zero detected probes is an inconclusive result. Before saying that no probe is connected, inspect OS USB/PnP and serial devices and try the intended backend's read-only probe/list operation. This matters for composite DAPLink/CMSIS-DAP and XDS110 devices whose debug interface and virtual COM port may appear under different Windows device classes.

## CCS-DSS Backend

CCS Debug Server Scripting is abbreviated as `ccs-dss` in this skill. Use it for CCS / CCS Theia / UniFlash tooling. Do not apply these commands to a CMake/OpenOCD project unless that project also has a valid CCS `.ccxml` and the user explicitly wants CCS DSS.

## Scope

- Requires TI CCS / CCS Theia or UniFlash scripting components.
- Requires a valid `targetConfigs/*.ccxml` for the active board and probe.
- Requires a built CCS `.out` file when loading or reloading firmware.
- Uses the debug probe selected inside `.ccxml`, so it is not limited to J-Link. It can also work with CCS-supported probes such as XDS110 when the `.ccxml` matches the connected hardware.
- Does not cover OpenOCD/GDB debugging. Use the separate backend below.

## Safety Rules

- Debug actions can halt the CPU and disturb real-time behavior. Warn the user before halting a motor, power stage, or time-sensitive control loop.
- Prefer UART logging, logic analyzer capture, or scoped register reads when non-intrusive observation is enough.
- Use symbol breakpoints before source-line breakpoints when possible. Source-line breakpoints require valid debug info and a line that maps to generated code.
- If a source-line breakpoint fails but symbol breakpoints work, treat it as a debug-info/source-line mapping issue first, not proof that the board or probe failed.
- If connect/list-core operations hang, close stale CCS, DSLite, UniFlash, J-Link, or debug-server processes before retrying.

## Script

From this skill package:

```powershell
python scripts\ccs_dss_debug.py <project-dir> probe --leave-running
```

When running from the repository root:

```powershell
python skills\mspm0-ccs\scripts\ccs_dss_debug.py <project-dir> probe --leave-running
```

Common commands:

```powershell
# Connect, read reset types and registers, then continue the target before disconnecting.
python scripts\ccs_dss_debug.py <project-dir> probe --leave-running

# Program the current Debug/Release .out and use System Reset after loading.
python scripts\ccs_dss_debug.py <project-dir> load --reset "System Reset" --leave-running

# Program, reset, and halt at main.
python scripts\ccs_dss_debug.py <project-dir> run-to-symbol --symbol main --load --reset "System Reset"

# Program, reset, and halt at a source line.
python scripts\ccs_dss_debug.py <project-dir> break-line --source empty.c --line 5 --load --reset "System Reset"

# Load debug symbols only; do not program flash.
python scripts\ccs_dss_debug.py <project-dir> load-symbols --symbol main --symbol UART_DMADoneTxCallback

# Load symbols only, reset, and halt at a source line without reprogramming flash.
python scripts\ccs_dss_debug.py <project-dir> break-line --source BSP/UART.c --line 75 --symbols --reset "System Reset"

# Load symbols only, reset, and halt at an address breakpoint.
python scripts\ccs_dss_debug.py <project-dir> break-address --address 0x2564 --symbols --reset "System Reset"

# Continue a currently connected target and disconnect the debug session.
python scripts\ccs_dss_debug.py <project-dir> run

# Halt and print PC/SP/LR.
python scripts\ccs_dss_debug.py <project-dir> halt
```

Useful options:

- `--ccs-run <path>`: explicit CCS scripting `run.bat`.
- `--ccxml <path>`: explicit target configuration.
- `--out <path>`: explicit program output file.
- `--timeout-ms <n>`: DSS script timeout.
- `--keep-js`: keep the temporary JavaScript for diagnosis.
- `--symbols`: load debug symbols from `.out` without programming flash for commands that support it.
- `--leave-running`: remove breakpoints and continue target execution before disconnecting, where supported by the chosen command.

When a project contains multiple `.ccxml` files or a command that needs a program finds multiple `.out` files, pass `--ccxml` or `--out` explicitly. The helper refuses to guess because selecting an old build or a target configuration for the wrong probe can produce misleading results or program unintended firmware.

## Verified Notes

Validated on LCKFB Tianmengxing MSPM0G3507 + CCS / CCS Theia + J-Link with a CCS project containing `targetConfigs/MSPM0G3507.ccxml` and `Debug/<project>.out`.

Observed working operations:

- `ds.configure(ccxml)` and `ds.openSession(/cortex|m0|MSPM0/i)`.
- `session.target.connect()`.
- `session.target.getResets()` returning reset types including Board Reset, CPU Reset, Core Reset, and System Reset.
- `session.registers.read("PC")`, `SP`, and `LR`.
- `session.memory.loadProgram(<project>.out)`.
- `session.symbols.load(<project>.out)` for no-flash symbol loading.
- `session.symbols.getAddress(<symbol>)` and `session.symbols.lookupSymbols(<address>)`.
- Symbol breakpoint at `main`.
- System Reset followed by `target.run()` halting at `main`.
- Source-line breakpoint at a line with generated code.
- Address breakpoint at a known function address.
- `target.run(false)` to leave the target running before disconnect.

One tested source line failed because no code was associated with that exact line. Another source line in the same file worked. For agents, that means source-line breakpoint failure should be reported precisely and retried with a symbol, nearby executable line, or address.

For non-invasive diagnosis after firmware has already been flashed, prefer `load-symbols`, `break-line --symbols`, or `break-address --symbols` over `--load`. These commands load debug information from the `.out` file without rewriting flash.

## Locked MSPM0 Recovery With CCS-DSS

Do not treat every Cortex connection failure as the same kind of lock. Before erasing anything, confirm the probe, target voltage, SWDIO/SWCLK, NRST, selected device, and `.ccxml`. Then distinguish these cases:

- Application startup, watchdog, clock, low-power, or peripheral faults can block a normal CPU attach even though the security policy is unchanged. Try a reset-aware attach, Wait for Debug, or Set Reset Mode before erasing.
- SWD can be enabled, disabled, or enabled with a 128-bit password in NONMAIN. If a password is configured, use the known password; never guess or substitute a BSL password.
- Invalid NONMAIN BCR, BSL, or CRC configuration can prevent normal boot and debug access. This can require a DSSM Factory Reset rather than a MAIN-only erase.
- DSSM commands are optional in security levels 0 and 1 and unavailable in security level 2. Factory Reset can also be disabled or password-protected by policy. Stop when the configured recovery policy does not permit the requested command.
- A held-low NRST, repurposed SWD pins, missing target power, or invalid clock supply is a hardware-access failure, not evidence that a destructive erase is needed.

The TI MSPM0 SDK documents the [Debug Subsystem Mailbox and Factory Reset tool](https://dev.ti.com/gallery/view/TIMSPGC/MSPM0_Factory_Reset_Tool/). A matching CCS support package also exposes the operations under `Scripts -> MSPM0xxxx_Commands` after launching the target configuration.

Choose the destructive command deliberately:

- **DSSM Mass Erase** erases MAIN application/code/data while preserving NONMAIN and its security policy. It will not remove a lock caused by an invalid or restrictive NONMAIN policy.
- **DSSM Factory Reset** erases MAIN and resets NONMAIN boot policies to defaults. Use it for invalid NONMAIN/BCR/BSL/CRC configuration or when the user explicitly wants the device configuration reset.
- **Password Authentication** grants the operation allowed by the configured policy when the correct SWD or Factory Reset password is known. The Factory Reset password and Bootloader Unlock password are separate values.

Safe sequence:

1. Obtain explicit user approval for loss of the existing firmware and configuration.
2. Use a `.ccxml` whose device and probe exactly match the hardware. For XDS110, verify the probe independently with `xdsdfu -e` or the OS device list.
3. Connect only the non-debug `CS_DAP` session and read `CFGAP_BOOTDIAG` when the Cortex-M0+ session cannot connect. Do not require a CPU connection for this read.
4. Select Mass Erase, Factory Reset, or password authentication from the diagnosis and known policy. Do not automatically escalate from one destructive command to another.
5. Prefer the `Auto` command when XDS110 NRST is wired and reliable. If TI GEL reports that the command was sent and reset was pulsed but then times out reconnecting to `SEC_AP`, classify the result as unknown and re-read BOOTDIAG; do not report success.
6. If Auto does not complete, use TI's power-up recovery sequence: power off, hold NRST low, power up while holding NRST low, execute the corresponding `Manual` DSSM command, and release NRST when prompted.
7. After a completed command, power-cycle when requested. Verify recovery independently by checking that BOOTDIAG changed, connecting the Cortex-M0+ session, reading registers, and performing a non-programming DSLite operation before loading firmware.

Verified recovery case, not a universal guarantee:

- Hardware/tool path: non-Tianmengxing MSPM0G3519 board, XDS110, CCS-DSS from CCS 20.2, and UniFlash 9.2.
- Initial symptoms: XDS110 was visible, but Cortex attach and DSLite failed with the NONMAIN debug-access/peripheral-configuration diagnostic.
- `CS_DAP` remained accessible and `CFGAP_BOOTDIAG` read `0x10136`; its low status contained `0x36`, matching the TI support package's invalid BCR/BSL/CRC recovery category.
- `MSPM0_Mailbox_FactoryReset_Auto` sent the command and pulsed NRST but timed out during `SEC_AP` reconnect. BOOTDIAG remained unchanged, so this was correctly treated as failure/unknown rather than success.
- `MSPM0_Mailbox_FactoryReset_Manual`, followed by a reset-button press, returned `Command execution completed`.
- BOOTDIAG changed to `0x6`; CCS-DSS then connected to Cortex-M0+, read PC/SP/LR, and DSLite listed `BlankCheck | MassErase` successfully.

BOOTDIAG encodings and recovery policy can vary by device family and support-package version. Use the target's current TI GEL diagnostics and TRM rather than copying the G3519 value table to another device.

### Tianmengxing MSPM0G3507 Interrupted-Flash Recovery

This is a separate, reproducible case from the non-Tianmengxing MSPM0G3519 DSSM case above.

- Hardware/tool path: LCKFB Tianmengxing MSPM0G3507, a CMSIS-DAPv2/DAPLink probe with UART bridge, and a TI MSPM0-capable OpenOCD build.
- Trigger: disconnecting the probe while flash programming is in progress.
- Observed signature: OpenOCD repeatedly reads `SWD DPIDR 0x6ba02477`, then reports `Could not find MEM-AP to control the core`. The same result at 24 MHz, 1 MHz, and 500 kHz indicates that the probe and SWD-DP are reachable; it is not, by itself, a generic wireless-disconnect error.
- The LCKFB web flasher uses the ROM UART BSL, not SWD. For Tianmengxing, use the board's BSL UART path; the default BSL UART pins are PA10 TX and PA11 RX, at 9600 baud, 8 data bits, no parity, and 1 stop bit.

Recovery boundary:

1. Obtain explicit approval to erase the existing application.
2. Enter hardware BSL: hold BSL, press and release RST, then release BSL. Start the host operation within the board's short BSL window (the LCKFB instructions state about 10 seconds).
3. Use the [LCKFB MSPM0 web flasher](https://wiki.lckfb.com/storage/html/mspm0-web-flasher/index.html) or TI's SDK BSL host under `tools/bsl/`. The host must connect, obtain device information, authenticate the BSL password, and issue Mass Erase; the button sequence alone only enters BSL and does not perform the erase.
4. TI SDK installations provide the all-`FF` development default in `tools/bsl/BSL_GUI_EXE/Input/BSL_Password32_Default.txt`. Use it only when the project has not intentionally changed the BSL password. Do not confuse the BSL password with an SWD or Factory Reset password.
5. Power-cycle or reset as requested by the host, then independently verify that the Cortex MEM-AP is available before programming the desired firmware.

Do not promise button-free recovery with an ordinary UART plus SWD connection. Software BSL invocation requires a still-running application that implements the invoke path; it does not help when the application cannot run or debug access is already unavailable. Full host automation also requires hardware capable of controlling both BSL and reset, such as deliberately wired probe GPIO or serial handshake outputs. A normal CMSIS-DAP UART/SWD connection does not imply those controls exist.

The web-flasher recovery path has been verified on Tianmengxing MSPM0G3507 after correctly entering hardware BSL. A subsequent read-only OpenOCD probe detected the Cortex-M0+ r0p1 core, reported four breakpoints and two watchpoints, and completed target examination, independently confirming that MEM-AP access was restored. The earlier direct CLI attempt received no BSL ACK because the board had not entered BSL correctly; direct CLI automation remains unverified and must not be presented as supported.

## When To Stop

Stop and ask the user before continuing if:

- The `.ccxml` probe does not match the connected hardware.
- The board controls motors, high-power outputs, or moving mechanisms and the next step will halt the CPU.
- The script can connect but loading a new `.out` would overwrite firmware the user did not ask to replace.
- OpenOCD files are present and the user appears to be using an OpenOCD workflow instead of CCS DSS.

## OpenOCD / GDB Backend

Use this backend when the detected probe and interface configuration are compatible with an MSPM0-capable OpenOCD installation.

### Verified Scope

The packaged helper was verified with:

- MSPM0G3507 hardware
- CMSIS-DAP / DAPLink probe
- an MSPM0-capable OpenOCD build containing `target/ti/mspm0.cfg` or `target/ti_mspm0.cfg`
- `interface/cmsis-dap.cfg`
- `arm-none-eabi-gdb`
- a TI Arm Clang-generated CCS `.out` ELF file

The helper can also use `.elf`, `.axf`, `.hex`, and `.bin` outputs. A raw `.bin` requires `--base-address`.

OpenOCD MSPM0 support commonly requires a TI MSPM0-capable build or TI extension branch. Do not assume an unrelated mainline OpenOCD installation can access MSPM0 correctly.

### Commands

```powershell
python scripts\openocd_debug.py <project-dir> probe
python scripts\openocd_debug.py <project-dir> flash
python scripts\openocd_debug.py <project-dir> registers
python scripts\openocd_debug.py <project-dir> run-to-symbol --symbol main
```

Other available actions:

```powershell
python scripts\openocd_debug.py <project-dir> run
python scripts\openocd_debug.py <project-dir> reset
```

Default config and fallback speeds:

```text
interface/cmsis-dap.cfg
target/ti/mspm0.cfg or target/ti_mspm0.cfg, auto-detected from the OpenOCD installation
24000,1000,500 kHz
```

Override them only when the connected probe, target support package, or project requires a different choice:

```powershell
python scripts\openocd_debug.py <project-dir> --interface <interface.cfg> --target <target.cfg> --speeds 24000,1000,500 probe
```

### Flash Behavior

`flash` auto-detects a compatible program output under the project directory, then performs:

```text
init
reset init
flash write_image erase <program>
verify_image <program>
reset run
shutdown
```

The helper searches CCS `Debug`/`Release`, generic `build`, CLion-style `cmake-build-*`, and the project root. Use `--program <path>` when several outputs exist and the automatic choice is ambiguous. Use `--no-verify` only when the user explicitly accepts losing verification.

### Connection Failures And Retries

The helper separates probe and transport failures from firmware failures. Its default retry order is `24000`, `1000`, then `500` kHz.

- `unable to find a matching CMSIS-DAP device`: probe discovery failure. Check USB or wireless DAPLink connectivity.
- `CMSIS-DAP command mismatch` or `CMD_CONNECT failed`: likely link corruption, wireless interruption, or another process holding the probe.
- target halt, SWD ACK, or DAP access failures: retry after reconnecting and lowering speed; if repeated, check wiring and ask whether the target needs manual unlock.
- verify failure: retry with a stable connection and lower speed before changing commands.

Do not run parallel OpenOCD operations against one probe. Flash, register reads, and GDB sessions can contend with each other.

### Locked Or Protected Targets

The helper intentionally does not perform automatic unlock, mass erase, or factory reset operations.

If it reports `target_locked_or_protected`, stop retries and ask the user to run their known manual unlock or recovery procedure. This avoids destructive recovery when a transient wireless failure merely resembles a target-access problem.

### OpenOCD Debug Safety

`probe` and `registers` briefly halt the current CPU state without resetting the target, then restore execution before the one-shot OpenOCD server exits. `run-to-symbol` intentionally resets and runs to the requested breakpoint. Before using debug actions on motors, power electronics, or other real-time control systems:

1. Warn the user that debug actions may pause control loops.
2. Put actuators into a safe state when possible.
3. Do not promise that a one-shot OpenOCD command can leave the target halted after the server exits. Use a separately managed persistent OpenOCD session when a paused target must remain under debugger control.

`run-to-symbol` refuses to attach when its GDB port is already occupied. Close the existing OpenOCD/debug session or choose an unused `--gdb-port`; do not attach to an unverified listener.
