# AirNode — Local Network File Explorer & Media Server

**Stack:** FastAPI · HTMX · Alpine.js · SQLite  
**Target:** Mobile browser over a local Wi-Fi hotspot (no internet required)

---

## Overview

AirNode exposes your PC's file system as a fast, browsable web interface reachable from any device on the same local network. It was built to work over a mobile hotspot without consuming cellular data.

Key capabilities:

- Full directory tree navigation with search, filters, and sort
- Local network discovery at `http://airnode.local:8000` via mDNS / Bonjour
- QR code connection page for phone access without typing the LAN IP
- **First-run PIN setup page** — choose your own PIN, no more random codes in a log file
- `--reset-pin` CLI flag for easy recovery if you forget your PIN
- File downloads, batch download (ZIP), and resumable chunked uploads
- Inline media viewer (images, video, audio, PDF, plain text) with HTTP 206 range streaming
- **Media hubs**: Cinema & TV, Music, Photo Gallery, and Recent/Starred sub-apps
- **Video transcoding** (H.264/AAC via ffmpeg) and **auto-generated thumbnails**
- **Chromecast casting** to a TV on the same network
- **ID3/EXIF metadata** for music and photos, embedded cover art
- **SQLite-backed** watch progress, recent files, and metadata caches
- **Single-instance detection** — launching a second copy opens the running instance instead of starting a second server
- **Stop controls** — Settings page, subtle footer button, and system tray "Stop AirNode"
- **System tray icon** with quick actions (open browser, QR, reset PIN, autostart, restart, stop, exit)
- **Autostart on login** via Windows Task Scheduler (no admin required)
- **In-app update checker** against GitHub Releases
- **Standalone executable** — no Python installation needed for end users
- Zero build-step frontend (HTMX + Alpine.js), all assets bundled locally (Lucide icons, Inter font) — works fully offline

---

## For End Users (Standalone Executable)

### Quick Start

1. Get `AirNode.exe` (or the installer `AirNode-Setup-<version>.exe`) from the latest [GitHub Release](https://github.com/Bensonmusonda/AirNode/releases).
2. Double-click it (or run it from a terminal).
3. On first run, your browser opens automatically to a **setup page** — choose a 4-10 digit PIN.
4. Connect your PC to a phone hotspot (or any shared Wi-Fi).
5. On your phone, open `http://airnode.local:8000` (or scan the QR code at `http://localhost:8000/connect`).
6. Enter the PIN you chose.

> **Note:** The released executable is built **windowed** (no console window). To quit, use the system tray icon → **Stop AirNode**, the **Stop server** button at the bottom-right of the web UI, or the **Stop AirNode** row in Settings.

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

### Already Running?

If AirNode is already running and you launch it again, it detects the running instance, opens your browser to it, and exits — it will **not** start a second server on another port.

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

On first run (no `.airnode-auth.json` exists), AirNode redirects all requests to a `/setup` page where you choose your own PIN. The setup page is restricted to **localhost** requests only, so a remote device on the hotspot cannot set the PIN before the host user does.

### Resetting the PIN

**From the CLI:**
```powershell
.venv\Scripts\python.exe airnode_server.py --reset-pin
```

**From the in-app menu** (if already logged in): Open the menu → "Reset PIN". This generates a new random PIN while keeping your current session valid.

### Building the Standalone Executable

```powershell
# Install build dependencies
pip install -r requirements-dev.txt

# Build the single-file executable (uses version from version.py)
python build.py

# Build a specific version (leading "v" allowed)
python build.py --version v2.0.1

# Build a folder (faster startup for dev testing; keeps console window)
python build.py --onedir

# Build without a console window (released onefile only)
python build.py --windowed

# Force a console window even when AIRNODE_CONSOLE=0 is set
python build.py --console
```

The output is `dist/AirNode-<version>.exe` (single file, no external dependencies) plus a `.sha256` checksum. The onedir dev build always keeps its console so URLs and startup logs stay visible; the released onefile is built windowed by CI.

**Note:** Some antivirus software may flag PyInstaller executables. This is a known false positive; the user may need to whitelist `AirNode.exe`.

### Access from Another Device

1. Connect your PC to a phone hotspot (or any shared Wi-Fi).
2. On the PC running AirNode, open `http://localhost:8000/connect` and scan the QR code with your phone.
3. You can also try the local network name directly: `http://airnode.local:8000`.
4. If that does not resolve on your device, use the fallback LAN URL written to the console when the server starts, or find the IP address your PC was assigned (`ipconfig`).
5. On your phone, open: `http://<PC-IP>:8000`.

`airnode.local` uses mDNS / Bonjour. It works well on iPhone, macOS, and many Android devices; the numeric IP address remains the reliable fallback.

---

## Project Layout

```
AirNode/
|-- main.py                   # FastAPI application (routes, auth, media hubs)
|-- airnode_server.py         # Server launcher: LAN discovery, CLI, single-instance probe
|-- airnode_auth.py           # PIN auth, session + CSRF management
|-- airnode_config.py         # Config dataclass + load/save
|-- audit.py                  # Audit logging (delete/rename/upload/etc.)
|-- autostart.py              # Windows Task Scheduler autostart
|-- cast.py                   # Chromecast discovery + playback (optional dep)
|-- db.py                     # SQLite: watch state, recent files, kv cache
|-- license_manager.py        # License key / trial management
|-- logging_config.py         # Logging setup
|-- media_meta.py             # ID3 tags, EXIF, cover art extraction
|-- paths.py                  # Frozen exe path resolution helpers
|-- tray.py                   # System tray icon
|-- updater.py                # GitHub Releases update check
|-- version.py                # Single source of truth for the version
|-- video_ffmpeg.py           # Thumbnails + transcoding via ffmpeg
|-- requirements.txt          # Production dependencies
|-- requirements-dev.txt      # Build dependencies (PyInstaller)
|-- build.spec                # PyInstaller spec
|-- build.py                  # Build convenience script
|-- installer.iss             # Inno Setup installer script
|-- setup.ps1                 # One-time venv + dependency install (dev)
|-- start.ps1                 # Start server in the background (dev)
|-- stop.ps1                  # Stop the running server (dev)
|-- .github/workflows/build.yml  # CI: tag-triggered release build
|-- assets/                   # App icon source
|-- static/
|   |-- css/                  # App stylesheets
|   |-- js/                   # App JavaScript
|   `-- vendor/               # Vendored JS/CSS/fonts (works offline)
|-- templates/
|   |-- index.html            # Main file explorer layout
|   |-- login.html            # PIN login page
|   |-- setup.html            # First-run PIN setup page
|   |-- connect.html          # QR code connection page
|   |-- settings.html         # Settings page (port, mDNS, autostart, license, power)
|   |-- cinema_hub.html       # Cinema & TV hub
|   |-- music_hub.html        # Music hub
|   |-- gallery_hub.html      # Photo gallery hub
|   |-- recent_hub.html       # Recent & starred hub
|   `-- partials/             # HTMX fragments
`-- docs/                     # FAQ, privacy policy, code-signing notes
```

---

## API Reference

### Pages

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Full-page index (redirects to last-visited folder) |
| `GET` | `/setup` | First-run PIN setup page |
| `POST` | `/setup` | Create the initial PIN |
| `GET` | `/login` | PIN login page |
| `POST` | `/login` | Create a signed browser session |
| `POST` | `/logout` | Clear the browser session |
| `POST` | `/reset-pin` | Generate a new PIN (requires active session) |
| `GET` | `/connect` | QR code and LAN URLs for connecting another device |
| `GET` | `/settings` | Settings page |
| `GET` | `/browse?path=<p>` | Directory listing (HTMX partial or full page) |
| `GET` | `/apps/cinema` | Cinema & TV hub |
| `GET` | `/apps/music` | Music hub |
| `GET` | `/apps/gallery` | Photo gallery hub |
| `GET` | `/apps/recent` | Recent & starred hub |

### Files & Uploads

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/download?path=<p>` | Download file as attachment |
| `GET` | `/download-batch?paths=<json>` | Download multiple items as a ZIP |
| `GET` | `/view?path=<p>` | Serve file inline with HTTP 206 range support |
| `POST` | `/delete` | Delete a file/folder |
| `POST` | `/delete-batch` | Delete multiple items |
| `POST` | `/rename` | Rename a file/folder |
| `POST` | `/new-folder` | Create a new folder |
| `GET` | `/properties?path=<p>` | File/folder properties |
| `POST` | `/upload/init` | Start a resumable chunked upload |
| `POST` | `/upload/chunk` | Upload a chunk |
| `POST` | `/upload/finalize` | Assemble chunks into the final file |
| `DELETE` | `/upload/cancel/{file_id}` | Cancel an upload session |
| `POST` | `/upload` | Simple single-file upload |

### Settings

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/settings/port` | Change the server port (restart required) |
| `POST` | `/settings/mdns/toggle` | Toggle mDNS advertisement (restart required) |
| `POST` | `/settings/autostart/toggle` | Toggle Windows autostart |
| `POST` | `/settings/restart` | Restart the AirNode process |

### System / Status

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/status` | Public: `{running, version, pid}` (used by single-instance probe) |
| `POST` | `/api/shutdown` | Stop AirNode (response delivered, then process exits) |
| `GET` | `/api/update/check` | Check GitHub Releases for a newer version |
| `GET` | `/api/license/status` | Current license / trial status |
| `POST` | `/api/license/activate` | Activate a product key |
| `POST` | `/api/license/revoke` | Remove the activated license |

### Browsing & Search

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/browse?path=<p>` | JSON directory listing |
| `GET` | `/api/search?q=<q>` | Recursive filename search |

### Media Hubs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/cinema/scan` | Scan & group videos into shows/movies |
| `GET` | `/api/cinema/folder` | List videos in a folder |
| `GET` | `/api/music/scan` | Scan & group audio into folder playlists |
| `GET` | `/api/music/folder` | List audio tracks in a folder |
| `GET` | `/api/media/watch-state` | Saved watch progress |
| `POST` | `/api/media/watch-state` | Update watch progress |
| `POST` | `/api/media/watch-state/clear` | Clear watch history |
| `GET` | `/api/recent` | Recently opened files |
| `POST` | `/api/recent/clear` | Clear recent-files history |

### Media Metadata & Playback

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/cover-art?path=<p>` | Embedded album art |
| `GET` | `/api/photo/info?path=<p>` | EXIF metadata (camera, date, GPS, ISO, etc.) |
| `GET` | `/api/video/thumbnail?path=<p>` | Auto-generated video thumbnail |
| `GET` | `/api/video/info?path=<p>` | Duration + resolution via ffprobe |
| `POST` | `/api/video/transcode` | Start background H.264/AAC transcoding |
| `GET` | `/api/video/transcode/status` | Transcode progress / availability |
| `GET` | `/api/subtitles?path=<p>` | SRT/VTT subtitles (converted to WebVTT) |
| `GET` | `/api/cast/devices` | Discover Chromecast devices |
| `POST` | `/api/cast/play` | Cast a video to a device |

### PWA

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/manifest.json` | Web App Manifest |
| `GET` | `/sw.js` | Service worker (offline shell) |

---

## CLI Flags

| Flag | Description |
|------|-------------|
| `--host <addr>` | Bind to a specific interface (default: `0.0.0.0`) |
| `--port <n>` | Listen on a specific port (default: `8000`) |
| `--no-mdns` | Disable mDNS/Bonjour advertisement |
| `--no-browser` | Do not auto-open the browser on startup |
| `--no-tray` | Do not show the system tray icon |
| `--verbose` | Enable debug-level logging |
| `--reset-pin` | Delete the current PIN; next launch shows setup page |
| `--install-autostart` | Register AirNode to start at Windows logon |
| `--uninstall-autostart` | Remove the autostart Task Scheduler entry |
| `--generate-key` | Generate a new license key and exit (developer tool) |
| `--reset-trial` | Reset the license trial timer and exit (developer tool) |
| `--version` | Show the AirNode version and exit |

---

## Versioning & Releases

The version is defined in `version.py` as a single `VERSION` constant. All version references read from this one source:

- **Build output filename**: `AirNode-<version>.exe` (e.g. `AirNode-2.0.1.exe`)
- **Windows file metadata**: Right-click the exe → Properties → Details shows the version
- **CLI**: `AirNode.exe --version` prints the version
- **UI footer**: The login and setup pages show `AirNode v<version>`
- **SHA-256 checksum**: A `.sha256` file is generated alongside each build for integrity verification

### Release workflow (CI)

Releases are built automatically by GitHub Actions when a `v*` tag is pushed:

```powershell
# 1. Bump the version in version.py to match the tag (e.g. 2.0.1)
# 2. Commit and push
git add version.py && git commit -m "Bump version to 2.0.1"
git push origin main

# 3. Tag and push — CI builds the release
git tag v2.0.1
git push origin v2.0.1
```

CI produces, in a new GitHub Release:

- `AirNode-<version>.exe` — windowed single-file executable
- `AirNode-<version>.exe.sha256` — checksum
- `AirNode-Setup-<version>.exe` — Inno Setup installer

**Golden rules:**

- Always bump `version.py` to match the tag (the in-app updater compares the GitHub tag minus `v` against `version.py`).
- Never re-point an existing tag — use a new version number for each release.

---

## License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.