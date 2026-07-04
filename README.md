# AirNode

**Local Network File Explorer & Media Server**  
Stack: FastAPI · HTMX · Alpine.js · Pico CSS  
Target: Mobile browser over a local Wi-Fi hotspot (no internet required)

---

## Overview

AirNode exposes your PC's file system as a fast, browsable web interface reachable from any device on the same local network. It was built to work over a mobile hotspot without consuming cellular data.

Key capabilities:
- Full directory tree navigation
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

### Access from another device

1. Connect your PC to a phone hotspot (or any shared Wi-Fi).
2. Find the IP address your PC was assigned:
   ```powershell
   ipconfig
   ```
   Look for the adapter connected to your hotspot (e.g., `192.168.43.x`).
3. On your phone, open: `http://<PC-IP>:8000`

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

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details. In short: you're free to use, modify, and distribute this code, including commercially, as long as the original copyright notice is kept.