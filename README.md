# AirNode

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
- Local PIN access gate with signed browser sessions
- Instant client-side file filtering
- File downloads with correct MIME disposition
- Inline media viewer (images, video, audio, PDF, plain text)
- HTTP 206 Partial Content streaming for seekable video/audio playback
- Zero build-step frontend (HTMX + Alpine.js + Pico CSS)

---

## Requirements

- Python 3.11 or newer
- Windows 10 / 11

---

## First-Time Setup

Open **PowerShell** in the project root and run:

```powershell
.\setup.ps1
```

This creates a `.venv/` virtual environment and installs all production dependencies from `requirements.txt`.

---

## Running the Server

### Manual start / stop

```powershell
# Start AirNode in the background (no console window)
.\start.ps1

# Stop AirNode
.\stop.ps1
```

`start.ps1` writes stdout to `airnode.log`, stderr (uvicorn startup messages and errors) to `airnode.log.err`, and the process ID to `airnode.pid`.  
`stop.ps1` reads the PID file and terminates the process cleanly.

On first run, AirNode creates `.airnode-auth.json` and prints a six-digit access
PIN to `airnode.log`. Keep that PIN for phones and other local devices. To reset
the PIN, stop AirNode, delete `.airnode-auth.json`, then start AirNode again.

### Access from another device

1. Connect your PC to a phone hotspot (or any shared Wi-Fi).
2. On the PC running AirNode, open:
   ```text
   http://localhost:8000/connect
   ```
   Then scan the QR code with your phone. The QR code uses the detected numeric
   LAN URL because that is the most reliable option across phones.
3. You can also try the local network name directly:
   ```text
   http://airnode.local:8000
   ```
4. If that does not resolve on your device, use the fallback LAN URL written to
   `airnode.log` when the server starts, or find the IP address your PC was assigned:
   ```powershell
   ipconfig
   ```
   Look for the adapter connected to your hotspot (e.g., `192.168.43.x`).
5. On your phone, open: `http://<PC-IP>:8000`

`airnode.local` uses mDNS / Bonjour. It works well on iPhone, macOS, and many
Android devices; the numeric IP address remains the reliable fallback.

---

## Autostart on Login (Background Service)

To have AirNode start automatically every time you log in to Windows — equivalent to a `systemd` service — run:

```powershell
.\install-autostart.ps1
```

This registers a **Windows Task Scheduler** task that launches `start.ps1` silently at logon. No administrator privileges are required.

To remove the autostart entry:

```powershell
.\uninstall-autostart.ps1
```

---

## Project Layout

```
AirNode/
├── main.py                   # FastAPI application
├── airnode_server.py         # Server launcher with LAN discovery
├── requirements.txt          # Production dependencies
├── setup.ps1                 # One-time venv + dependency install
├── start.ps1                 # Start server in the background
├── stop.ps1                  # Stop the running server
├── install-autostart.ps1     # Register Task Scheduler autostart
├── uninstall-autostart.ps1   # Remove autostart registration
├── static/
│   └── vendor/               # Vendored JS/CSS (works offline)
│       ├── alpine.min.js
│       ├── htmx.min.js
│       └── pico.min.css
└── templates/
    ├── index.html            # Full-page layout and Alpine component
    └── partials/
        ├── breadcrumbs.html  # Breadcrumb navigation fragment
        └── file_list.html    # Directory listing fragment (HTMX target)
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Full-page index |
| `GET` | `/login` | PIN login page |
| `POST` | `/login` | Create a signed browser session |
| `POST` | `/logout` | Clear the browser session |
| `GET` | `/connect` | QR code and LAN URLs for connecting another device |
| `GET` | `/browse?path=<p>` | Directory listing (HTMX partial or full page) |
| `GET` | `/download?path=<p>` | Download file as attachment |
| `GET` | `/view?path=<p>` | Serve file inline with range support |
| `GET` | `/api/browse?path=<p>` | JSON directory listing |

---

## Development

Run with hot-reload during development:

```powershell
.venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Run the normal server launcher with LAN discovery:

```powershell
.venv\Scripts\python.exe airnode_server.py --host 0.0.0.0 --port 8000
```

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details. In short: you're free to use, modify, and distribute this code, including commercially, as long as the original copyright notice is kept.
