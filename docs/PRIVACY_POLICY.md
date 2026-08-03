# AirNode Privacy Policy

**Last updated:** 2026-08-03

## Overview

AirNode is a local network file explorer and media server that runs on
your own computer. This policy explains what data AirNode collects, where
it is stored, and what we never do with it.

## Data Storage

All data AirNode creates is stored **locally on your computer**, next to
the AirNode executable:

| Data | File / Location | Purpose |
|------|----------------|---------|
| PIN hash & session secret | `.airnode-auth.json` | Secure login (salted SHA-256, never plaintext) |
| Login lockout records | `.airnode-lockout.json` | Brute-force protection |
| Config (port, host, mDNS, autostart) | `airnode-config.json` | Your preferences |
| Scan cache (30-min TTL) | `.airnode_cache/` | Faster directory/media scans |
| Upload temp sessions (24-h TTL) | `.airnode_upload_temp/` | Resumable chunked uploads |
| Watch progress | `.airnode_watch_state.json` | "Continue watching" in Cinema Hub |
| Update-check cache (6-h TTL) | `.airnode_update_cache.json` | Avoids repeated GitHub API calls |
| License state | `.airnode-license.json` | Trial start date / activated key |
| Logs (rotating, 5MB × 4) | `airnode.log*` | Error reporting & support |

## What We Never Collect

- **No telemetry.** AirNode does not phone home, send analytics, or upload
  usage statistics.
- **No file contents.** Your files never leave your device. File scans and
  media streaming happen entirely over your local network.
- **No personal identifiers.** We do not collect your name, email, or unique
  device IDs.

## Network Communication

The only outbound network request AirNode makes is the **update check**
(`/api/update/check`), which queries the public GitHub Releases API for the
latest version number, then opens your browser to the GitHub page when an
update is available. No identifying information is sent.

## Local Network Access

AirNode binds to your local network (default `0.0.0.0`) so phones and other
devices on the same Wi-Fi can browse files. Anyone who knows your PIN (or
the device's network) can access the web UI. You can change or disable the
PIN at any time via the Settings page or the tray menu.

## Your PIN

Your PIN is never stored in plaintext. Only a salted SHA-256 hash is saved.
There is no way to recover a forgotten PIN — the "Reset PIN" option in the
tray menu clears it so you can set a new one.

## Deleting Your Data

Uninstalling AirNode (via the installer or by deleting the folder) removes
all local data. Log files, caches, and auth config are deleted with the app
directory. You can also manually delete any of the `.airnode_*` files listed
above at any time while AirNode is stopped.

## Third-Party Services

- **GitHub** — used only for the optional update check and download page.
- **Inno Setup / PyInstaller** — build-time tools, not runtime services.

## Changes to This Policy

We may update this policy as AirNode evolves. The date at the top reflects
the latest revision. Significant changes will be announced in release notes.

## Contact

Questions about this policy? Open an issue at:
https://github.com/Bensonmusonda/AirNode