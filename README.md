# Modbus Multi-Session Industrial Client

A cross-platform desktop GUI for connecting to, reading from, and writing to Modbus-enabled industrial control system (ICS) devices. Supports multiple simultaneous connections, per-session polling, and both Modbus TCP and Modbus RTU (serial) protocols.

Compatible with **Windows** and **Linux**.

---

## Requirements

- **Python 3.8 or later**
- **pymodbus 3.x** (3.0 or later — see version note below)
- **tkinter** (bundled with Python on Windows; may need separate install on Linux)

### Install dependencies

**Windows:**
```
python -m pip install pymodbus
```

**Linux (Debian/Ubuntu):**
```
pip install pymodbus
sudo apt install python3-tk
```

### pymodbus version compatibility

This application uses the **keyword-argument API** introduced in pymodbus 3.5, where `count` and `value` must be passed as named arguments rather than positional ones. This is the current convention for pymodbus 3.5 and later:

```
python -m pip install "pymodbus>=3.5"
```

If you see an error like:

```
Read exception: ModbusClientMixin.read_holding_registers() takes 2 positional arguments but 3 were given
```

your installed version of pymodbus is older than 3.5. Upgrade it with:

```
python -m pip install --upgrade pymodbus
```

> **Important — Windows multi-Python environments:** If you have more than one Python installation, always use `python -m pip install` rather than just `pip install`. This ensures the package installs into the same Python that will run the script. The application will display the exact command to use if it cannot find pymodbus at startup.

---

## Running the Application

```
python modbus_gui_multi.py
```

The application window opens immediately. No configuration files or environment variables are needed.

---

## Interface Overview

The window is divided into three areas:

```
┌──────────────────────────────────────────────────────────────┐
│  ◈ MODBUS  MULTI-SESSION INDUSTRIAL CLIENT        2/3 connected │
├─────────────┬────────────────────────────────────────────────┤
│             │  ● PLC-01  192.168.1.10              ▶ CONNECT  │
│ CONNECTIONS │  ⚙ Edit                                         │
│             │ ─────────────────────────────────────────────── │
│  ● PLC-01   │  [ ↓ READ ] [ ↑ WRITE ] [ ⟳ POLL ]            │
│  ○ PLC-02   │                                                  │
│  ● RTU-Dev  │                                                  │
│             ├────────────────────┬───────────────────────────┤
│ [+ Add]     │  SESSION LOG       │  GLOBAL LOG               │
│             │                    │                           │
│ Connect All │                    │                           │
│ Disconnect  │                    │                           │
└─────────────┴────────────────────┴───────────────────────────┘
```

**Sidebar** — lists all configured connections with live status indicators. Click any row to switch to that session.

**Workspace** — shows the Read, Write, and Poll controls for the currently selected session.

**Session Log** — activity log for the selected session. Switches content when you select a different session.

**Global Log** — aggregates events from all sessions simultaneously, tagged with the source connection name.

---

## Adding a Connection

1. Click the **+** button at the top of the sidebar, or right-click in the sidebar and choose **Add Connection**.
2. Fill in the connection details (see below).
3. Click **Add Connection** to save. The new session appears in the sidebar.
4. Click **▶ CONNECT** in the workspace header or the session's context menu to connect.

### TCP Connection Fields

| Field | Description | Default |
|---|---|---|
| Label | A friendly name shown in the sidebar | New Connection |
| Host / IP | IP address or hostname of the Modbus TCP server | 192.168.1.1 |
| Port | TCP port — Modbus standard is 502 | 502 |
| Timeout (s) | Seconds before a connection attempt is abandoned (1–300) | 5 |
| Default Unit ID | Modbus slave/unit ID used in read and write operations (1–247) | 1 |

### RTU (Serial) Connection Fields

| Field | Description | Typical Values |
|---|---|---|
| Label | Friendly name shown in the sidebar | — |
| Serial Port | System name of the COM/serial port | `COM3` (Windows), `/dev/ttyUSB0` (Linux) |
| Baud Rate | Communication speed in bits per second | 9600, 19200, 115200 |
| Parity | Error-checking bit | N (None), E (Even), O (Odd) |
| Stop Bits | Number of stop bits | 1 or 2 |
| Byte Size | Number of data bits per byte | 8 (almost always) |
| Default Unit ID | Modbus slave address on the RS-485 bus (1–247) | 1 |

> **Tip:** Click **TCP** or **RTU** at the top of the dialog to switch between modes. Only the relevant fields are shown for the selected mode.

---

## Managing Connections

### Connection Status Indicators

| Symbol | Colour | Meaning |
|---|---|---|
| ○ | Grey | Disconnected |
| ◌ | Yellow | Connecting… |
| ● | Green | Connected |
| ● | Red | Error — connection failed |

### Context Menu

Right-click any session row in the sidebar to access:

- **Connect** / **Disconnect** — connect or disconnect this session
- **Rename** — change the session label without losing configuration
- **Remove** — delete the session (prompts to disconnect first if active)

### Bulk Actions

The buttons at the bottom of the sidebar act on all sessions at once:

- **Connect All** — attempt to connect every disconnected session in parallel
- **Disconnect All** — close all active connections

### Editing a Connection

Click **⚙ Edit** in the workspace header while a session is selected. The configuration dialog re-opens pre-filled with the current values. If the session is currently connected, you will be prompted to disconnect before editing.

---

## Reading Data

Select a session, then click the **↓ READ** tab.

| Field | Description |
|---|---|
| Type | The Modbus register area to read from |
| Address | Starting register or coil address (0–65535, decimal or `0x` hex) |
| Count | Number of consecutive registers/coils to read |
| Unit | Slave/unit ID to address — overrides the session default for this read |

**Register types:**

| Type | Function Code | Description |
|---|---|---|
| Holding Registers | FC03 | Read/write 16-bit values — most common for process data |
| Input Registers | FC04 | Read-only 16-bit values from sensors/ADCs |
| Coils | FC01 | Read/write single-bit outputs (relays, digital outputs) |
| Discrete Inputs | FC02 | Read-only single-bit inputs (switches, digital inputs) |

Click **READ** to execute. Results appear in the table, which now shows six columns:

| Column | Description |
|---|---|
| Label | User-defined name for this address (amber text when set) |
| Address | Register or coil address |
| Dec | Decimal value |
| Hex | Hexadecimal value |
| Bin | Binary representation |
| State | ON / OFF for bit types |

> **Protocol limits enforced:** Maximum 125 registers or 2000 coils per request. Requests outside these limits are rejected before they are sent.

### Labelling Registers

Double-click any row in the results table to assign a name to that address. Enter a label and click OK — the Label column updates immediately and the row is highlighted in amber. Labels are saved per session and per register type, so the same address in Holding Registers and Input Registers can carry different names. Leave the field blank and click OK to clear a label.

Labels persist for the lifetime of the session and are re-applied every time new read results arrive for that address.

### Layout

The results table occupies most of the workspace. A draggable divider separates the data area from the log panel below — drag the divider up or down to give the table more or less space.

---

## Writing Data

Select a session, then click the **↑ WRITE** tab.

| Field | Description |
|---|---|
| Type | What to write |
| Address | Target register or coil address (0–65535, decimal or `0x` hex) |
| Unit | Slave/unit ID |
| Value(s) | One or more values, comma-separated for multi-register writes |

**Write types:**

| Type | Description |
|---|---|
| Holding Register | Write a single 16-bit register (FC06) |
| Multiple Registers | Write a block of 16-bit registers in one request (FC16) |
| Coil | Write a single coil ON or OFF (FC05) |
| Multiple Coils | Write a block of coils in one request (FC15) |

### Value Format

Values can be entered as decimal (`100`), hexadecimal (`0x0064`), or binary (`0b01100100`). For multi-register or multi-coil writes, separate values with commas:

```
100, 200, 0xFF, 0
```

### Write Once

Click **⚡ WRITE ONCE** to send the write immediately. If **Confirm before write** is ticked, a summary dialog appears first.

### Continuous Write

The **Continuous Write** section repeats the write automatically at a fixed interval:

| Field | Description |
|---|---|
| Interval (s) | Seconds between writes — minimum 0.1 s |
| Last | Timestamp of the most recent write |

Click **▶ START WRITE POLLING** to begin. Click **■ STOP WRITE POLLING** to stop. The confirmation dialog is always suppressed during continuous write — configure and verify your values with **WRITE ONCE** first.

> **Warning:** Continuous write sends repeated commands to the device at the configured interval. Use with care in production environments.

### Confirm Before Write

When ticked (the default), a confirmation dialog appears before each manual write. This is automatically bypassed during continuous write.

### Format Converter

The converter at the bottom of the Write tab translates between decimal, hexadecimal, and binary without performing a write. Enter a value in any notation and click the appropriate button.

---

## Polling

Select a session, then click the **⟳ POLL** tab. The tab contains two independent sections.

### Continuous Read

Repeats the Read tab operation at a fixed interval, updating the results table each time.

| Field | Description |
|---|---|
| Interval (s) | Seconds between reads — minimum 0.1 s |
| Last | Timestamp of the most recent successful read |

Click **▶ START READ POLLING** to begin. Click **■ STOP READ POLLING** to stop.

### Continuous Write

Repeats the Write tab operation at a fixed interval without any confirmation prompt.

| Field | Description |
|---|---|
| Interval (s) | Seconds between writes — minimum 0.1 s |
| Last | Timestamp of the most recent write |

Click **▶ START WRITE POLLING** to begin. Click **■ STOP WRITE POLLING** to stop.

Both controls are also available directly on the **↑ WRITE** tab under the Continuous Write section.

> **Multiple sessions can be polled simultaneously.** Each session has its own independent read and write polling threads — up to two threads per session. Changing settings on one session does not affect another.

> **Note:** Read and write poll settings are saved per session. Switching sessions and back resumes polling with the original settings. Both polling loops are automatically stopped when a session disconnects or the application closes.

---

## Logs

### Session Log

Shows all activity for the currently selected session. When you switch sessions, the log reloads with that session's full history (up to 500 entries). Click **Clear** to wipe the display without losing the underlying history.

### Global Log

Shows events from all sessions in chronological order, prefixed with the source session label. Useful for monitoring multiple devices at a glance. Click **Clear** to clear the display.

**Log entry colours:**

| Colour | Meaning |
|---|---|
| Green | Success / connected |
| Red | Error |
| Amber | Warning / disconnected |
| Blue | Informational (read/write initiated) |
| White | Data |

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Enter` | Confirm / submit in dialogs |
| `Escape` | Close / cancel dialogs |

---

## Common Issues

### "Read/Write exception: takes 2 positional arguments but 3 were given"

Your pymodbus version is older than 3.5. The pymodbus 3.5 release changed `count` and `value` from positional to keyword-only arguments. Upgrade to fix it:

```
python -m pip install --upgrade pymodbus
```

### "pymodbus not found" at startup

The application is running under a different Python than the one where pymodbus was installed. The Global Log will show the exact command to fix this:

```
"C:\Users\you\AppData\Local\Programs\Python\Python310\python.exe" -m pip install pymodbus
```

Copy and run that command, then restart the application.

### Cannot connect — "Connection refused or timed out"

- Confirm the device is powered on and reachable on the network (`ping <ip>`)
- Check that the IP address and port are correct (Modbus TCP default is **502**)
- Confirm no firewall is blocking port 502
- For RTU: confirm the correct COM port and that the baud rate, parity, and stop bits match the device configuration
- Try increasing the Timeout value in the connection settings

### Modbus error on read/write

The device returned a Modbus exception code. Common causes:

- **Address out of range** — the device does not have a register at that address
- **Wrong register type** — trying to read a coil address as a holding register
- **Unit ID mismatch** — the device is configured for a different slave address
- **Count too large** — request exceeds the device's per-request limit; try a smaller count

### RTU port not opening on Linux

Your user account may not have permission to access the serial port:

```
sudo usermod -aG dialout $USER
```

Log out and back in for the change to take effect.

---

## Security Notes

- This tool sends Modbus commands directly to the configured endpoints with no additional authentication layer. Modbus TCP has no built-in authentication.
- Always ensure you have **explicit authorisation** before connecting to any ICS device.
- The **Confirm Before Write** option is enabled by default and should remain on in production environments to prevent accidental changes.
- Input validation is enforced on all addresses (0–65535), register counts (1–125 / 1–2000), unit IDs (1–247), and register values (0–65535) before any packet is transmitted.
- Poll intervals are clamped to a minimum of 0.1 seconds to prevent unintended network flooding.

---

## License

This software is provided as-is for authorised use by qualified personnel on systems they have permission to access. Misuse against systems without authorisation may be illegal.
