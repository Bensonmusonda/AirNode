# AirNode - Remote File explorer on local network

**Local Network File Explorer & Media Server**  
Stack: FastAPI · HTMX · Alpine.js · Pico CSS  
Target: Mobile browser over a local Wi-Fi hotspot (no internet required)

---

## Overview

AirNode exposes your PC's file system as a fast, browsable web interface reachable from any device on the same local network. It was built to work over a mobile hotspot without consuming cellular data.

Key capabilities:
- Full directory tree navigation
- Local network discovery at `http://airnode.local:8000` via mDNS / Bonjour
- QR code connection page for phone access without typing the LAN IP
- **First-run PIN setup page** — choose your own PIN, no more random codes in a log file
- `--reset-pin` CLI flag for easy recovery if you forget your PIN
- Instant client-side file filtering
- File downloads with correct MIME disposition
- Inline media viewer (images, video, audio, PDF, plain text)
- HTTP 206 Partial Content streaming for seekable video/audio playback
- **Standalone executable** — no Python installation needed for end users
- Zero build-step frontend (HTMX + Alpine.js + Pico CSS)
- **All assets bundled locally** (Lucide icons, Inter font) — works fully offline

---

## For End Users (Standalone Executable)

### Quick Start

1. Get `AirNode.exe` from the developer.
2. Double-click it (or run it from a terminal).
3. On first run, your browser opens automatically to a **setup page** — choose a 4-10 digit PIN.
4. Connect your PC to a phone hotspot (or any shared Wi-Fi).
5. On your phone, open `http://airnode.local:8000` (or scan the QR code at `http://localhost:8000/connect`).
6. Enter the PIN you chose.

### If You Forget Your PIN

Open a terminal (Command Prompt or PowerShell) in the same folder as `AirNode.exe` and run:

```text
AirNode.exe --reset-pin
```

Then start AirNode again — you'll be asked to choose a new PIN.

### Autostart on Login

```text
AirNode.exe --install-autostart
AirNode.exe --uninstall-autostart
```

This registers/removes a Windows Task Scheduler task that launches AirNode silently at logon. No administrator privileges required.

---

## For Developers

### Requirements

- Python 3.11 or newer
- Windows 10 / 11

### First-Time Setup (Development)

```powershell
.\setup.ps1
```

This creates a `.venv/` virtual environment and installs all production dependencies from `requirements.txt`.

### Running the Server (Development)

```powershell
# Start AirNode in the background (no console window)
.\start.ps1

# Stop AirNode
.\stop.ps1
```

Or run directly with hot-reload:

```powershell
.venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### First-Run PIN Setup

On first run (no `.airnode-auth.json` exists), AirNode redirects all requests to a `/setup` page where you choose your own PIN. This replaces the old flow that auto-generated a random PIN and printed it to the log.

The setup page is restricted to **localhost** requests only, so a remote device on the hotspot cannot set the PIN before the host user does.

### Resetting the PIN

**From the CLI:**
```powershell
.venv\Scripts\python.exe airnode_server.py --reset-pin
```

**From the in-app menu** (if already logged in): Open the menu -> "Reset PIN". This generates a new random PIN while keeping your current session valid.

### Building the Standalone Executable

```powershell
# Install build dependencies
pip install -r requirements-dev.txt

# Build the executable (uses version from version.py)
python build.py

# Build a specific version
python build.py --version 1.1.0

# Build a folder (faster startup for dev testing)
python build.py --onedir
```

The output is `dist/AirNode-<version>.exe` -- a single file with no external dependencies. Share it directly.

**Note:** Some antivirus software may flag PyInstaller executables. This is a known false positive; the user may need to whitelist `AirNode.exe`.

### Access from Another Device

1. Connect your PC to a phone hotspot (or any shared Wi-Fi).
2. On the PC running AirNode, open:
   ```text
   http://localhost:8000/connect
   ```
   Then scan the QR code with your phone.
3. You can also try the local network name directly:
   ```text
   http://airnode.local:8000
   ```
4. If that does not resolve on your device, use the fallback LAN URL written to the console when the server starts, or find the IP address your PC was assigned:
   ```powershell
   ipconfig
   ```
   Look for the adapter connected to your hotspot (e.g., `192.168.43.x`).
5. On your phone, open: `http://<PC-IP>:8000`

`airnode.local` uses mDNS / Bonjour. It works well on iPhone, macOS, and many Android devices; the numeric IP address remains the reliable fallback.

---

## Project Layout

```
AirNode/
|-- main.py                   # FastAPI application
|-- airnode_server.py         # Server launcher with LAN discovery + CLI
|-- airnode_auth.py           # PIN auth, session management
|-- paths.py                  # Frozen exe path resolution helpers
|-- requirements.txt          # Production dependencies
|-- requirements-dev.txt      # Build dependencies (PyInstaller)
|-- build.spec                # PyInstaller spec
|-- build.py                  # Build convenience script
|-- setup.ps1                 # One-time venv + dependency install (dev)
|-- start.ps1                 # Start server in the background (dev)
|-- stop.ps1                  # Stop the running server (dev)
|-- install-autostart.ps1     # Register Task Scheduler autostart (legacy)
|-- uninstall-autostart.ps1   # Remove autostart registration (legacy)
|-- static/
|   |-- css/                  # App stylesheets
|   |-- js/                   # App JavaScript
|   `-- vendor/               # Vendored JS/CSS/fonts (works offline)
|       |-- alpine.min.js
|       |-- htmx.min.js
|       |-- pico.min.css
|       |-- lucide.min.js
|       |-- inter-font.css
|       `-- fonts/            # Inter TTF files
`-- templates/
    |-- index.html            # Full-page layout and Alpine component
    |-- login.html            # PIN login page
    |-- setup.html            # First-run PIN setup page
    |-- connect.html          # QR code connection page
    `-- partials/             # HTMX fragments
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Full-page index |
| `GET` | `/setup` | First-run PIN setup page |
| `POST` | `/setup` | Create the initial PIN |
| `GET` | `/login` | PIN login page |
| `POST` | `/login` | Create a signed browser session |
| `POST` | `/logout` | Clear the browser session |
| `POST` | `/reset-pin` | Generate a new PIN (requires active session) |
| `GET` | `/connect` | QR code and LAN URLs for connecting another device |
| `GET` | `/browse?path=<p>` | Directory listing (HTMX partial or full page) |
| `GET` | `/download?path=<p>` | Download file as attachment |
| `GET` | `/view?path=<p>` | Serve file inline with range support |
| `GET` | `/api/browse?path=<p>` | JSON directory listing |

---

## CLI Flags

| Flag | Description |
|------|-------------|
| `--host <addr>` | Bind to a specific interface (default: `0.0.0.0`) |
| `--port <n>` | Listen on a specific port (default: `8000`) |
| `--no-mdns` | Disable mDNS/Bonjour advertisement |
| `--reset-pin` | Delete the current PIN; next launch shows setup page |
| `--install-autostart` | Register AirNode to start at Windows logon |
| `--uninstall-autostart` | Remove the autostart Task Scheduler entry |
| `--version` | Show the AirNode version and exit |

---

## Versioning & Releases

The version is defined in `version.py` as a single `VERSION` constant. All version references read from this one source:

- **Build output filename**: `AirNode-<version>.exe` (e.g. `AirNode-1.0.0.exe`)
- **Windows file metadata**: Right-click the exe -> Properties -> Details shows the version
- **CLI**: `AirNode.exe --version` prints the version
- **UI footer**: The login and setup pages show `AirNode v<version>`
- **SHA-256 checksum**: A `.sha256` file is generated alongside each build for integrity verification

### Release workflow

```powershell
# 1. Bump the version in version.py
# 2. Tag and push
git tag v1.0.0 && git push --tags
# 3. Build
python build.py --version 1.0.0
# 4. Upload dist/AirNode-1.0.0.exe to GitHub Releases
```

## License

This project is licensed under the MIT License -- see the [LICENSE](LICENSE) file for details. In short: you're free to use, modify, and distribute this code, including commercially, as long as the original copyright notice is kept.
