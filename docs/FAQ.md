# AirNode FAQ

### What is AirNode?

AirNode is a local network file explorer and media server that runs on your
Windows PC. It turns your computer into a shareable drive that any phone,
tablet, or laptop on the same Wi-Fi can browse — no cloud, no cables, no
upload limits.

### Is my data sent to the cloud?

**No.** AirNode is 100% local. Files are streamed directly between your PC
and the device on your local network. The only outbound request is an
optional update check against the public GitHub API.

### How do I install AirNode?

Download `AirNode-Setup-x.x.x.exe` from the GitHub Releases page and run
it. It installs to your user folder (no admin required) and adds an entry
to the Start Menu. You can also use the portable `.exe` directly.

### Why does Windows show a SmartScreen warning?

Unsigned builds show "Windows protected your PC" until the publisher earns
reputation. Click **More info → Run anyway** to proceed, or wait for a
signed release (see [Code Signing](CODE_SIGNING.md)).

### How do I set up a PIN?

On first launch, AirNode opens the **Setup** page. Choose a PIN of 6–10
digits. The PIN gates access to the web UI from any device. Your PIN is
stored only as a salted SHA-256 hash.

### I forgot my PIN. How do I reset it?

Right-click the AirNode tray icon → **Reset PIN**, then relaunch AirNode.
It will open the Setup page so you can choose a new one. Alternatively run:

```
AirNode.exe --reset-pin
```

### How do I access AirNode from my phone?

1. Make sure your phone and PC are on the same Wi-Fi.
2. Click the **QR code** icon in AirNode's header (or the tray menu →
   Show QR Code).
3. Scan it with your phone's camera — it opens AirNode's web UI on your
   phone.

### Can I change the port?

Yes. Open **Settings → Port**, enter a new value (1–65535), and click
**Apply**. Restart AirNode for the change to take effect.

### Why did AirNode switch to a different port?

If port 8000 is already in use by another program, AirNode automatically
picks the next available port and prints it in the console. This prevents
a crash on startup.

### How do I stop AirNode?

- Right-click the tray icon → **Exit**, or
- Press **Ctrl+C** in the terminal window, or
- Run `stop.ps1` (development).

### Does AirNode start automatically?

You can enable autostart from **Settings → Start with Windows** toggle, or
from the tray menu **Autostart: On/Off**. The installer can also register
autostart during setup.

### Can I use AirNode over the internet?

Not directly. AirNode is designed for **local networks only**. If you want
remote access, you can set up a VPN (e.g. Tailscale) and connect through
the virtual network — AirNode doesn't need any changes for that.

### What file types can I stream?

AirNode streams audio (MP3, FLAC, M4A, WAV, OGG, AAC, Opus), video (MP4,
MKV, AVI, MOV, WebM), images (JPG, PNG, GIF, WEBP, SVG), PDFs, and text/code
files directly in the browser.

### Can I upload files from my phone?

Yes. Open AirNode on your phone, navigate to the folder, and use the upload
button (or drag-and-drop in the desktop browser). Large files upload in
resumable chunks — an interrupted upload can be continued later.

### What is the trial / license key for?

AirNode is open-source (AGPL-3.0). The 14-day trial is a tracking state that
shows "Trial Mode" in Settings; entering a purchased license key clears it.
All features remain available — the license is a supporter mechanism, not a
DRM wall.

### How do I get a license key?

Contact the developer or open an issue on the GitHub repository. A key
looks like `ABNODE-XXXXX-XXXXX-XXXXX-XXXXX` and works with any build of
AirNode.

### Where are my logs?

Logs are written to `airnode.log` next to the executable, rotating at 5 MB
(up to 3 backups). They contain timestamps, module names, and error details
to help with troubleshooting.

### How do I uninstall AirNode?

Run **Uninstall AirNode** from the Start Menu, or use
**Settings → Apps → AirNode → Uninstall**. This removes the app, its
config/auth files, and the autostart task.

### Is there a PWA / mobile app?

Not yet — the web UI works great on mobile browsers, and PWA support is on
the roadmap (Phase 5).