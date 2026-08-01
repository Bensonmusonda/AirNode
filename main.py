import aiofiles
import math
import os
import sys
import shutil
import string
import ctypes
import mimetypes
import json
import traceback
import zipfile
import io
import threading
from urllib.parse import quote
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi import UploadFile, Form, File
from fastapi.concurrency import run_in_threadpool
import time

from airnode_auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    check_login_lockout,
    create_pin,
    create_session_token,
    has_auth_config,
    register_login_failure,
    register_login_success,
    reset_pin,
    verify_pin,
    verify_session_token,
)
from paths import get_resource_dir, get_data_dir
from version import VERSION


app = FastAPI(title="AirNode")

_resource_dir = get_resource_dir()
_data_dir = get_data_dir()

app.mount("/static", StaticFiles(directory=str(_resource_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(_resource_dir / "templates"))


PUBLIC_PATHS = {"/login", "/setup", "/favicon.ico"}
PUBLIC_PREFIXES = ("/static/",)


# ==============================================================================
# Scan Result Cache (disk-backed, 30-minute TTL)
# ==============================================================================

_CACHE_DIR = _data_dir / ".airnode_cache"
_CACHE_TTL = 1800  # 30 minutes
_cache_lock = threading.Lock()


def _cache_path(key: str) -> Path:
    _CACHE_DIR.mkdir(exist_ok=True)
    return _CACHE_DIR / f"{key}.json"


def _read_cache(key: str) -> dict | None:
    """Return cached result if fresh, else None."""
    p = _cache_path(key)
    try:
        if p.exists() and (time.time() - p.stat().st_mtime) < _CACHE_TTL:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _write_cache(key: str, data: dict) -> None:
    p = _cache_path(key)
    try:
        with _cache_lock, p.open("w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _invalidate_cache(key: str) -> None:
    try:
        _cache_path(key).unlink(missing_ok=True)
    except Exception:
        pass


def _next_url(request: Request) -> str:
    next_url = request.query_params.get("next", "/")
    return next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"


def _login_redirect(request: Request) -> RedirectResponse:
    current = request.url.path
    if request.url.query:
        current = f"{current}?{request.url.query}"
    return RedirectResponse(url=f"/login?next={quote(current, safe='')}", status_code=303)


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    path = request.url.path

    # First-run setup: if no PIN has been created yet, force all requests
    # to the /setup page (except /setup itself and static assets).
    if not has_auth_config():
        if path == "/setup" or path.startswith("/static/"):
            return await call_next(request)
        return RedirectResponse(url="/setup", status_code=303)

    if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)

    if verify_session_token(request.cookies.get(COOKIE_NAME)):
        return await call_next(request)

    if request.headers.get("HX-Request"):
        return Response(
            "Authentication required.",
            status_code=401,
            headers={"HX-Redirect": "/login"},
        )
    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "Authentication required."})
    return _login_redirect(request)


# ==============================================================================
# System Initialization and Root Detection
# ==============================================================================

def get_system_roots() -> list[Path]:
    """Detects and returns all available root directories or mount points on the host system."""
    if sys.platform == "win32":
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        return [
            Path(f"{letter}:\\")
            for letter in string.ascii_uppercase
            if bitmask & (1 << (ord(letter) - ord('A')))
        ]
    else:
        return [Path("/")]

ROOTS = get_system_roots()

# Allowed file extensions that can be rendered inline using browser capabilities
VIEWABLE_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg',
    'pdf',
    'mp4', 'webm',
    'mp3', 'ogg', 'wav',
    'txt', 'md', 'py', 'js', 'ts', 'json', 'html', 'css',
    'rs', 'c', 'cpp', 'go', 'java', 'sh',
}


# ==============================================================================
# Access Control and Security
# ==============================================================================

def is_path_allowed(target: Path) -> bool:
    """Validates if the resolved target path lies within allowed root directories.
    Expects an already-resolved Path — do not pass unresolved paths here."""
    return any(
        target == root or root in target.parents
        for root in ROOTS
    )


# ==============================================================================
# Utility Helpers
# ==============================================================================

def format_size(size_bytes: int | None) -> str:
    """Formats raw byte sizes into human-readable representations (KB, MB, etc.)."""
    if size_bytes is None:
        return ""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

def build_breadcrumbs(path_str: str) -> list[dict]:
    """Generates structured breadcrumb objects for UI navigation based on the active path."""
    if not path_str or path_str in ("/", ""):
        return []
    parts = [p for p in path_str.replace("\\", "/").split("/") if p]
    crumbs = []
    for i, part in enumerate(parts):
        path = "/".join(parts[:i + 1])
        # Windows drive letters (e.g. "C:") need a trailing slash so
        # resolve_target returns the drive root, not the current working directory.
        if i == 0 and part.endswith(":"):
            path += "/"
        crumbs.append({"label": part, "path": path})
    return crumbs

def resolve_target(path: str) -> Path | None:
    """Resolves raw path parameters into absolute, OS-specific Path instances.
    Always returns a resolved (canonicalised) path or None for the root sentinel."""
    if sys.platform == "win32":
        if not path:
            return None
        return Path(path.replace("/", "\\")).resolve()
    else:
        if not path or path == "/":
            return Path("/")
        # Strip leading slash before joining to avoid double-slash artefacts,
        # then resolve to canonicalise symlinks and dot-segments.
        return (Path("/") / path.lstrip("/")).resolve()

def scan_directory(target: Path) -> list[dict]:
    """Scans a directory and returns entry metadata.
    Uses os.scandir so DirEntry.is_file() and DirEntry.stat() reuse the
    cached inode data from the readdir syscall where the OS supports it
    (Linux, macOS). The is_file() result is computed once per entry."""
    try:
        with os.scandir(target) as it:
            scan_entries = list(it)
    except OSError:
        return []

    # Evaluate is_file() once here; the lambda in the sort key reuses it.
    typed: list[tuple[bool, os.DirEntry]] = []
    for e in scan_entries:
        try:
            typed.append((e.is_file(), e))
        except OSError:
            typed.append((False, e))

    # Directories first, then files, both case-insensitive by name.
    typed.sort(key=lambda t: (t[0], t[1].name.lower()))

    entries = []
    for is_file, entry in typed:
        size = None
        mtime = 0.0
        try:
            stat_res = entry.stat()
            mtime = stat_res.st_mtime
            if is_file:
                size = stat_res.st_size
        except (PermissionError, OSError):
            pass

        name = entry.name
        ext = name.rsplit(".", 1)[-1].lower() if ("." in name and is_file) else ""

        entries.append({
            "name": name,
            "type": "file" if is_file else "directory",
            "size_bytes": size,
            "size_display": format_size(size),
            "path": entry.path.replace("\\", "/"),
            "ext": ext,
            "viewable": ext in VIEWABLE_EXTENSIONS,
            "mtime": mtime,
        })
    return entries

def _render(request: Request, template: str, context: dict, status_code: int = 200):
    """Utility helper to render templates with consistent request contexts."""
    return templates.TemplateResponse(request=request, name=template, context=context, status_code=status_code)


# ==============================================================================
# HTTP Routes and Endpoints
# ==============================================================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Renders the PIN login page."""
    client_key = request.client.host if request.client else "unknown"
    lockout_remaining = check_login_lockout(client_key)
    return _render(request, "login.html", {
        "next_url": _next_url(request),
        "error": "",
        "lockout_seconds": math.ceil(lockout_remaining) if lockout_remaining > 0 else 0,
        "version": VERSION,
    })


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    pin: str = Form(...),
    next_url: str = Form("/"),
):
    """Authenticates with the local AirNode PIN and sets a signed session."""
    client_key = request.client.host if request.client else "unknown"

    lockout_remaining = check_login_lockout(client_key)
    if lockout_remaining > 0:
        return _render(request, "login.html", {
            "next_url": next_url,
            "error": "",
            "lockout_seconds": math.ceil(lockout_remaining),
        }, status_code=429)

    if not verify_pin(pin):
        register_login_failure(client_key)
        return _render(request, "login.html", {
            "next_url": next_url,
            "error": "That PIN did not match.",
            "lockout_seconds": 0,
        })

    register_login_success(client_key)
    redirect_to = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    """Renders the first-run PIN setup page.

    Only accessible when no auth config exists yet. The middleware
    redirects here on first run; once a PIN is set, /setup redirects
    to /login instead.
    """
    if has_auth_config():
        return RedirectResponse(url="/login", status_code=303)
    return _render(request, "setup.html", {"error": "", "version": VERSION})


@app.post("/setup", response_class=HTMLResponse)
def setup_submit(
    request: Request,
    pin: str = Form(...),
    pin_confirm: str = Form(...),
):
    """Creates the initial PIN on first run.

    Restricted to localhost requests so a remote device on the hotspot
    cannot set the PIN before the host user does.
    """
    if has_auth_config():
        return RedirectResponse(url="/login", status_code=303)

    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return _render(request, "setup.html", {
            "error": "For security, the PIN must be set from this computer (localhost).",
        }, status_code=403)

    pin = pin.strip()
    pin_confirm = pin_confirm.strip()

    if not pin:
        return _render(request, "setup.html", {"error": "PIN cannot be empty."})
    if len(pin) < 4:
        return _render(request, "setup.html", {"error": "PIN must be at least 4 digits."})
    if not pin.isdigit():
        return _render(request, "setup.html", {"error": "PIN must contain only digits."})
    if pin != pin_confirm:
        return _render(request, "setup.html", {"error": "PINs do not match."})

    create_pin(pin)
    response = RedirectResponse(url="/login", status_code=303)
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.post("/reset-pin")
def reset_pin_route():
    """Generates a new PIN for a logged-in user who forgot the old one.
    The current session (and any other device already logged in) stays
    valid — only future logins need the new PIN. Gated purely by the auth
    middleware: reaching this route already proves prior authentication,
    so no extra confirmation is required here."""
    new_pin = reset_pin()
    return JSONResponse({"pin": new_pin})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Renders the main layout and root drive/directory listing."""
    if sys.platform == "win32":
        entries = [
            {"name": str(r), "type": "directory", "size_display": "", "path": str(r).replace("\\", "/"), "ext": "", "viewable": False, "mtime": 0.0}
            for r in ROOTS
        ]
        current_path, breadcrumbs = "/", []
    else:
        target = Path("/")
        entries = await run_in_threadpool(scan_directory, target)
        current_path, breadcrumbs = "/", []

    return _render(request, "index.html", {
        "entries": entries,
        "current_path": current_path,
        "breadcrumbs": breadcrumbs,
        "platform": sys.platform,
    })


@app.get("/connect", response_class=HTMLResponse)
def connect(request: Request):
    """Displays connection details and a QR code for phone access."""
    try:
        lan_urls = json.loads(os.environ.get("AIRNODE_LAN_URLS", "[]"))
    except json.JSONDecodeError:
        lan_urls = []

    primary_url = os.environ.get("AIRNODE_PRIMARY_URL") or (lan_urls[0] if lan_urls else "")

    return _render(request, "connect.html", {
        "primary_url": primary_url,
        "lan_urls": lan_urls,
        "mdns_url": os.environ.get("AIRNODE_MDNS_URL", ""),
        "qr_url": os.environ.get("AIRNODE_QR_URL", primary_url),
        "qr_path": os.environ.get("AIRNODE_QR_PATH", ""),
        "qr_error": os.environ.get("AIRNODE_QR_ERROR", ""),
    })


# === HTMX Directory Browsing ===

@app.get("/browse", response_class=HTMLResponse)
async def browse(request: Request, path: str = ""):
    """Handles partial content rendering for HTMX and fallback full-page renders.
    scan_directory is offloaded to a threadpool so blocking stat() calls never
    stall the asyncio event loop."""
    target = resolve_target(path)
    is_htmx = "HX-Request" in request.headers

    if target is None:
        entries = [
            {"name": str(r), "type": "directory", "size_display": "", "path": str(r).replace("\\", "/"), "ext": "", "viewable": False, "mtime": 0.0}
            for r in ROOTS
        ]
        ctx = {"entries": entries, "current_path": "/", "breadcrumbs": [], "platform": sys.platform}
        return _render(request, "partials/file_list.html" if is_htmx else "index.html", ctx)

    if not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path!r}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path!r}")

    entries = await run_in_threadpool(scan_directory, target)
    current_path = str(target).replace("\\", "/")
    breadcrumbs = build_breadcrumbs(current_path)
    ctx = {"entries": entries, "current_path": current_path, "breadcrumbs": breadcrumbs, "platform": sys.platform}

    return _render(request, "partials/file_list.html" if is_htmx else "index.html", ctx)


# === File Download Endpoint ===

@app.get("/download")
def download(path: str):
    """Streams files as octet-stream attachments for user downloading."""
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        path=target,
        filename=target.name,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
    )

@app.post("/delete")
def delete_item(request: Request, path: str = Form(...)):
    """Deletes a file or directory securely if it passes validation."""
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found.")
        
    item_type = "Folder" if target.is_dir() else "File"
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
            
        # Return a trigger header to tell HTMX to refresh the current directory view
        return Response(
            status_code=200,
            headers={
                "HX-Trigger": json.dumps({
                    "refresh-directory": {},
                    "show-toast": {"message": f"{item_type} deleted successfully", "type": "success"}
                })
            }
        )
    except Exception as e:
        # This will print out exactly why Windows rejected it in your terminal logs
        print(f"\n[AirNode Deletion Error]: {str(e)}")
        traceback.print_exc()
        return Response(status_code=500, content=f"Failed to delete {item_type.lower()}: {str(e)}")

# --- Batch Delete Endpoint ---
@app.post("/delete-batch")
async def delete_batch(paths: str = Form(...)):
    """Deletes multiple files/folders."""
    try:
        path_list = json.loads(paths)
        for p in path_list:
            target = resolve_target(p)
            # Ensure path is valid and within roots
            if target and is_path_allowed(target) and target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
        return Response(
            status_code=200,
            headers={
                "HX-Trigger": json.dumps({
                    "show-toast": {"message": "Items deleted successfully", "type": "success"}
                })
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Batch Download Endpoint ---
@app.get("/download-batch")
async def download_batch(paths: str):
    try:
        path_list = json.loads(paths)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid paths parameter.")
    
    # In-memory ZIP buffer
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for p in path_list:
            target = resolve_target(p)
            if target and is_path_allowed(target) and target.exists():
                if target.is_dir():
                    for root, _, files in os.walk(target):
                        for file in files:
                            file_path = Path(root) / file
                            zip_file.write(file_path, file_path.relative_to(target.parent))
                else:
                    zip_file.write(target, target.name)
    
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="archive.zip"'}
    )

UPLOAD_TEMP_DIR = _data_dir / ".airnode_upload_temp"
UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)

def cleanup_expired_upload_sessions(ttl_hours: int = 24):
    """Purges incomplete chunk upload sessions older than ttl_hours."""
    if not UPLOAD_TEMP_DIR.exists():
        return
    now = time.time()
    cutoff = now - (ttl_hours * 3600)
    try:
        for session_dir in UPLOAD_TEMP_DIR.iterdir():
            if session_dir.is_dir():
                meta_file = session_dir / "session.json"
                updated_at = 0
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            updated_at = data.get("updated_at", 0)
                    except Exception:
                        pass
                else:
                    updated_at = session_dir.stat().st_mtime
                
                if updated_at < cutoff:
                    try:
                        shutil.rmtree(session_dir)
                    except Exception as e:
                        print(f"[AirNode Cleanup Error] Failed to delete expired session {session_dir.name}: {e}")
    except Exception as e:
        print(f"[AirNode Cleanup Error] Iteration failed: {e}")

def sanitize_file_id(file_id: str) -> str:
    """Sanitizes file_id for safe use as a directory name."""
    clean = "".join(c for c in file_id if c.isalnum() or c in ("-", "_")).strip()
    return clean if clean else "default_upload_session"

@app.post("/upload/init")
async def upload_init(
    filename: str = Form(...),
    file_size: int = Form(...),
    target_path: str = Form(""),
    file_id: str = Form(...),
    total_chunks: int = Form(...),
    force_overwrite: str = Form("false")
):
    cleanup_expired_upload_sessions()

    cleaned_path_str = target_path.strip()
    target_dir = resolve_target(cleaned_path_str) if cleaned_path_str and cleaned_path_str != "undefined" else None
    if target_dir is None:
        target_dir = ROOTS[0] if ROOTS else Path("C:/")

    if not is_path_allowed(target_dir):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target folder does not exist.")

    safe_filename = Path(filename).name
    destination = target_dir / safe_filename

    # Check collision
    if destination.exists() and force_overwrite != "true":
        return JSONResponse({
            "collision": True,
            "filename": safe_filename,
            "resumed": False,
            "received_chunks": []
        })

    safe_id = sanitize_file_id(file_id)
    session_dir = UPLOAD_TEMP_DIR / safe_id
    session_file = session_dir / "session.json"

    if session_dir.exists() and session_file.exists():
        try:
            async with aiofiles.open(session_file, "r", encoding="utf-8") as f:
                content = await f.read()
                session_data = json.loads(content)

            received_chunks = []
            for item in session_dir.iterdir():
                if item.name.startswith("chunk_"):
                    try:
                        idx = int(item.name.split("_")[1])
                        received_chunks.append(idx)
                    except ValueError:
                        pass

            received_chunks.sort()
            session_data["updated_at"] = time.time()
            async with aiofiles.open(session_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(session_data))

            return JSONResponse({
                "collision": False,
                "resumed": True,
                "file_id": safe_id,
                "received_chunks": received_chunks,
                "filename": safe_filename
            })
        except Exception:
            pass

    session_dir.mkdir(parents=True, exist_ok=True)
    session_data = {
        "file_id": safe_id,
        "filename": safe_filename,
        "target_path": str(target_dir),
        "file_size": file_size,
        "total_chunks": total_chunks,
        "created_at": time.time(),
        "updated_at": time.time()
    }
    async with aiofiles.open(session_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(session_data))

    return JSONResponse({
        "collision": False,
        "resumed": False,
        "file_id": safe_id,
        "received_chunks": [],
        "filename": safe_filename
    })

@app.post("/upload/chunk")
async def upload_chunk(
    file_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk_file: UploadFile = File(...)
):
    safe_id = sanitize_file_id(file_id)
    session_dir = UPLOAD_TEMP_DIR / safe_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Upload session expired or not found.")

    chunk_path = session_dir / f"chunk_{chunk_index}"
    try:
        async with aiofiles.open(chunk_path, "wb") as f:
            while True:
                buf = await chunk_file.read(1024 * 256)
                if not buf:
                    break
                await f.write(buf)
    finally:
        await chunk_file.close()

    session_file = session_dir / "session.json"
    if session_file.exists():
        try:
            async with aiofiles.open(session_file, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())
            data["updated_at"] = time.time()
            async with aiofiles.open(session_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data))
        except Exception:
            pass

    received_chunks = []
    for item in session_dir.iterdir():
        if item.name.startswith("chunk_"):
            try:
                received_chunks.append(int(item.name.split("_")[1]))
            except ValueError:
                pass
    received_chunks.sort()

    return JSONResponse({
        "status": "ok",
        "chunk_index": chunk_index,
        "received_chunks": received_chunks
    })

@app.post("/upload/finalize")
async def upload_finalize(
    file_id: str = Form(...),
    force_overwrite: str = Form("false")
):
    safe_id = sanitize_file_id(file_id)
    session_dir = UPLOAD_TEMP_DIR / safe_id
    session_file = session_dir / "session.json"

    if not session_dir.exists() or not session_file.exists():
        raise HTTPException(status_code=404, detail="Upload session not found.")

    try:
        async with aiofiles.open(session_file, "r", encoding="utf-8") as f:
            session_data = json.loads(await f.read())
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read upload session data.")

    total_chunks = session_data["total_chunks"]
    safe_filename = session_data["filename"]
    target_dir = Path(session_data["target_path"])

    if not is_path_allowed(target_dir) or not target_dir.exists():
        raise HTTPException(status_code=400, detail="Invalid or non-existent target folder.")

    missing_chunks = []
    for i in range(total_chunks):
        chunk_path = session_dir / f"chunk_{i}"
        if not chunk_path.exists():
            missing_chunks.append(i)

    if missing_chunks:
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing chunks", "missing_chunks": missing_chunks}
        )

    destination = target_dir / safe_filename
    if destination.exists() and force_overwrite != "true":
        return JSONResponse(
            status_code=200,
            content={"collision": True, "filename": safe_filename}
        )

    temp_dest = target_dir / f".{safe_filename}.tmp_{int(time.time())}"
    try:
        async with aiofiles.open(temp_dest, "wb") as out_file:
            for i in range(total_chunks):
                chunk_path = session_dir / f"chunk_{i}"
                async with aiofiles.open(chunk_path, "rb") as chunk_file:
                    while True:
                        data = await chunk_file.read(1024 * 512)
                        if not data:
                            break
                        await out_file.write(data)

        if destination.exists():
            destination.unlink()
        temp_dest.rename(destination)

    except Exception as e:
        if temp_dest.exists():
            temp_dest.unlink()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Assembly failed: {str(e)}")
    finally:
        try:
            shutil.rmtree(session_dir)
        except Exception:
            pass

    return JSONResponse(
        status_code=200,
        content={"status": "success", "filename": safe_filename},
        headers={
            "HX-Trigger": json.dumps({
                "refresh-directory": {},
                "show-toast": {"message": f"Successfully uploaded {safe_filename}", "type": "success"}
            })
        }
    )

@app.delete("/upload/cancel/{file_id}")
async def upload_cancel(file_id: str):
    safe_id = sanitize_file_id(file_id)
    session_dir = UPLOAD_TEMP_DIR / safe_id
    if session_dir.exists():
        try:
            shutil.rmtree(session_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse({"status": "cancelled"})

@app.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request, 
    path: str = Form(""), 
    force_overwrite: str = Form("false"),
    file: UploadFile = File(...)
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file payload provided.")

    try:
        # 1. Resolve Path
        cleaned_path_str = path.strip()
        target_dir = resolve_target(cleaned_path_str) if cleaned_path_str and cleaned_path_str != "undefined" else None
        if target_dir is None:
            target_dir = ROOTS[0] if ROOTS else Path("C:/")

        if not target_dir.exists() or not target_dir.is_dir():
            return HTMLResponse(status_code=400, content="Target folder does not exist.")

        safe_filename = Path(file.filename).name
        destination = target_dir / safe_filename

        # 2. Collision Guard Rails Check
        if destination.exists() and force_overwrite != "true":
            # Stop right here and tell the client-side UI to pop the modal!
            return HTMLResponse(
                status_code=200,
                content="",
                headers={
                    "HX-Trigger": json.dumps({
                        "file-collision-detected": {"filename": safe_filename}
                    })
                }
            )

        # 3. Stream binary chunks to disk — open once, write all chunks, close once.
        async def stream_to_disk():
            async with aiofiles.open(destination, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 256)  # 256 KB chunks
                    if not chunk:
                        break
                    await f.write(chunk)

        await stream_to_disk()

    except Exception as e:
        print("\n" + "="*60 + "\n[AirNode Upload Error Traceback]")
        traceback.print_exc()
        print("="*60 + "\n")
        return HTMLResponse(status_code=500, content=f"Upload error: {str(e)}")
    finally:
        await file.close()

    return HTMLResponse(
        status_code=200,
        content="",
        headers={
            "HX-Trigger": json.dumps({
                "refresh-directory": {},
                "show-toast": {"message": f"Successfully uploaded {safe_filename}", "type": "success"}
            })
        }
    )


@app.get("/properties")
async def get_properties(path: str):
    """Calculates granular system metrics and permissions for the properties dialog."""
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found.")
        
    try:
        stat = target.stat()
        created = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_ctime))
        modified = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
        
        return {
            "name": target.name,
            "path": str(target).replace("\\", "/"),
            "type": "Folder" if target.is_dir() else "File",
            "size": format_size(stat.st_size) if target.is_file() else "Directory containing items",
            "created": created,
            "modified": modified
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rename")
def rename_item(request: Request, path: str = Form(...), new_name: str = Form(...)):
    """Renames a file or folder securely within allowed roots."""
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found.")
        
    # Standardize the new name to remove any accidental path injection characters
    clean_name = Path(new_name).name
    if not clean_name:
        raise HTTPException(status_code=400, detail="Invalid name.")
        
    destination = target.parent / clean_name
    
    # Safety Check: Prevent overwriting an existing file/folder
    if destination.exists():
        return Response(
            status_code=400, 
            content="An item with that name already exists."
        )
        
    item_type = "Folder" if target.is_dir() else "File"
    try:
        os.rename(target, destination)
        
        # Return a 200 with headers to refresh the directory and fire a success toast
        return Response(
            status_code=200,
            headers={
                "HX-Trigger": json.dumps({
                    "refresh-directory": {},
                    "show-toast": {"message": f"{item_type} renamed successfully", "type": "success"}
                })
            }
        )
    except Exception as e:
        print(f"\n[AirNode Rename Error]: {str(e)}")
        return Response(status_code=500, content=f"Failed to rename {item_type.lower()}: {str(e)}")

@app.post("/new-folder")
def create_new_folder(request: Request, current_path: str = Form(...), folder_name: str = Form(...)):
    """Creates a new subfolder inside the designated parent path securely."""
    # Resolve and validate the target parent location
    parent_dir = resolve_target(current_path)
    if parent_dir is None or not is_path_allowed(parent_dir):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not parent_dir.is_dir():
        raise HTTPException(status_code=404, detail="Parent directory not found.")
        
    # Ensure the folder name does not contain illegal characters or path injections
    clean_name = Path(folder_name).name
    if not clean_name:
        raise HTTPException(status_code=400, detail="Invalid folder name.")
        
    new_dir_path = parent_dir / clean_name
    
    # Check if a folder or file with that name already exists
    if new_dir_path.exists():
        return Response(
            status_code=400, 
            content="An item with that name already exists."
        )
        
    try:
        # Create the folder safely
        new_dir_path.mkdir(exist_ok=False)
        
        return Response(
            status_code=200,
            headers={
                "HX-Trigger": json.dumps({
                    "refresh-directory": {},
                    "show-toast": {"message": "Folder created successfully", "type": "success"}
                })
            }
        )
    except Exception as e:
        print(f"\n[AirNode Folder Creation Error]: {str(e)}")
        return Response(status_code=500, content=f"Failed to create folder: {str(e)}")
# ==============================================================================
# Streaming File Viewer Endpoint (with HTTP Range request support)
# ==============================================================================

# Explicit MIME overrides — Python's mimetypes module commonly gets these
# wrong on Windows (e.g. .m4a → None, .flac → None, .mkv → None).
_MIME_OVERRIDES: dict[str, str] = {
    # Audio
    ".mp3":  "audio/mpeg",
    ".m4a":  "audio/mp4",
    ".aac":  "audio/aac",
    ".ogg":  "audio/ogg",
    ".oga":  "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".wav":  "audio/wav",
    ".weba": "audio/webm",
    # Video
    ".mp4":  "video/mp4",
    ".webm": "video/webm",
    ".mkv":  "video/x-matroska",
    ".avi":  "video/x-msvideo",
    ".mov":  "video/quicktime",
    ".m4v":  "video/mp4",
}

CHUNK = 1024 * 512  # 512 KB chunks


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """
    Parse a Range: bytes=START-END header.
    Returns (start, end) as inclusive byte indices.
    Raises ValueError on malformed input.
    """
    if not range_header.startswith("bytes="):
        raise ValueError("Only byte ranges are supported.")
    range_spec = range_header[len("bytes="):]
    # Only handle the first range in a multi-range header
    first = range_spec.split(",")[0].strip()
    start_str, _, end_str = first.partition("-")
    if not start_str:
        # Suffix range: bytes=-N  →  last N bytes
        suffix = int(end_str)
        start  = file_size - suffix
        end    = file_size - 1
    else:
        start = int(start_str)
        end   = int(end_str) if end_str else file_size - 1
    if start < 0 or end >= file_size or start > end:
        raise ValueError(f"Range {start}-{end} out of bounds for size {file_size}.")
    return start, end


def _iter_range(path: Path, start: int, end: int):
    """Yield bytes from `path` in the range [start, end] inclusive."""
    remaining = end - start + 1
    with open(path, "rb") as f:
        f.seek(start)
        while remaining > 0:
            chunk = f.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@app.get("/view")
def view_file(request: Request, path: str):
    """Serves file content inline, supporting HTTP 206 Partial Content ranges for media streaming."""
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    mime = _MIME_OVERRIDES.get(target.suffix.lower()) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    file_size = target.stat().st_size

    # Common headers present on every response
    base_headers = {
        "Content-Disposition": f'inline; filename="{target.name}"',
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
    }

    range_header = request.headers.get("range")

    # ── No Range header: serve the full file (200 OK) ──────────────
    if not range_header:
        def iter_full():
            with open(target, "rb") as f:
                while chunk := f.read(CHUNK):
                    yield chunk

        return StreamingResponse(iter_full(), media_type=mime, headers=base_headers)

    # ── Range request: serve a partial response (206) ──────────────
    try:
        start, end = _parse_range(range_header, file_size)
    except ValueError:
        # 416 Range Not Satisfiable
        raise HTTPException(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"},
            detail="Invalid range.",
        )

    partial_length = end - start + 1
    partial_headers = {
        **base_headers,
        "Content-Range":  f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(partial_length),
    }

    return StreamingResponse(
        _iter_range(target, start, end),
        status_code=206,
        media_type=mime,
        headers=partial_headers,
    )


# === REST API Endpoints ===

@app.get("/api/browse")
async def browse_json(path: str = ""):
    """Returns directory contents as structured JSON for API consumers."""
    target = resolve_target(path)
    if target is None:
        return {"roots": [str(r).replace("\\", "/") for r in ROOTS]}
    if not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Not found.")
    entries = await run_in_threadpool(scan_directory, target)
    return {"current_path": str(target).replace("\\", "/"), "entries": entries}


# ==============================================================================
# Luxury Sub-Apps & Media API Endpoints
# ==============================================================================

WATCH_STATE_FILE = _data_dir / ".airnode_watch_state.json"

def _load_watch_state() -> dict:
    if WATCH_STATE_FILE.exists():
        try:
            with open(WATCH_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_watch_state(data: dict):
    try:
        with open(WATCH_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WatchState Save Error] {e}")

@app.get("/api/media/watch-state")
def get_watch_state():
    """Returns saved watch progress timestamps."""
    return _load_watch_state()

@app.post("/api/media/watch-state")
async def save_watch_progress(request: Request):
    """Updates watch timestamp for a video file."""
    body = await request.json()
    path = body.get("path")
    current_time = body.get("currentTime", 0)
    duration = body.get("duration", 0)
    if not path:
        raise HTTPException(status_code=400, detail="Missing path")
    
    state = _load_watch_state()
    pct = (current_time / duration * 100) if duration > 0 else 0
    state[path] = {
        "currentTime": current_time,
        "duration": duration,
        "percent": round(pct, 1),
        "completed": pct >= 92.0,
        "updatedAt": time.time()
    }
    _save_watch_state(state)
    return state[path]

@app.get("/api/subtitles")
def get_subtitles(path: str):
    """Finds matching .srt or .vtt subtitle file for video and serves WebVTT."""
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    
    # Check for direct vtt/srt path or sibling subtitle file
    srt_path = target.with_suffix(".srt")
    vtt_path = target.with_suffix(".vtt")

    sub_file = None
    if vtt_path.exists():
        sub_file = vtt_path
    elif srt_path.exists():
        sub_file = srt_path
    else:
        # Search directory for any srt/vtt file containing same base name
        parent = target.parent
        if parent.exists():
            stem = target.stem.lower()
            for f in parent.iterdir():
                if f.suffix.lower() in [".srt", ".vtt"] and stem in f.name.lower():
                    sub_file = f
                    break

    if not sub_file or not sub_file.exists():
        return Response("WEBVTT\n\n", media_type="text/vtt")

    try:
        content = sub_file.read_text(encoding="utf-8", errors="ignore")
        if sub_file.suffix.lower() == ".srt":
            # Convert SRT to WebVTT format
            content = "WEBVTT\n\n" + content.replace(",", ".")
        elif not content.startswith("WEBVTT"):
            content = "WEBVTT\n\n" + content
        return Response(content, media_type="text/vtt")
    except Exception as e:
        return Response("WEBVTT\n\n", media_type="text/vtt")

import re

def _parse_episode_info(filename: str, parent_dir_name: str = "") -> dict:
    """Parses S01E01, 1x01, Ep 01 patterns and show names."""
    # Pattern 1: S01E01 or s1e2
    m = re.search(r'[sS](\d{1,2})[eE](\d{1,2})', filename)
    if m:
        season_num = int(m.group(1))
        ep_num = int(m.group(2))
        show_title = filename[:m.start()].strip(" .-_[]()")
        if not show_title:
            show_title = parent_dir_name or "TV Series"
        return {
            "is_series": True,
            "show": show_title.title(),
            "season": f"Season {season_num}",
            "season_num": season_num,
            "episode": f"S{season_num:02d}E{ep_num:02d}",
            "ep_num": ep_num,
            "title": filename
        }

    # Pattern 2: 1x01
    m = re.search(r'(\d{1,2})x(\d{1,2})', filename)
    if m:
        season_num = int(m.group(1))
        ep_num = int(m.group(2))
        show_title = filename[:m.start()].strip(" .-_[]()")
        if not show_title:
            show_title = parent_dir_name or "TV Series"
        return {
            "is_series": True,
            "show": show_title.title(),
            "season": f"Season {season_num}",
            "season_num": season_num,
            "episode": f"S{season_num:02d}E{ep_num:02d}",
            "ep_num": ep_num,
            "title": filename
        }

    # Pattern 3: Ep 01 or Episode 1
    m = re.search(r'(?:[eE][pP]?|Episode)\s*(\d{1,2})', filename, re.IGNORECASE)
    if m:
        ep_num = int(m.group(1))
        show_title = parent_dir_name or filename[:m.start()].strip(" .-_[]()") or "TV Series"
        return {
            "is_series": True,
            "show": show_title.title(),
            "season": "Season 1",
            "season_num": 1,
            "episode": f"E{ep_num:02d}",
            "ep_num": ep_num,
            "title": filename
        }

    return {"is_series": False, "title": filename}

@app.get("/api/cinema/scan")
def scan_cinema_library(path: str = "", bust: int = 0):
    """Scans and groups video files into TV Series, Seasons, Episodes, and Movies.
    Results are cached for 30 minutes. Pass ?bust=1 to force a fresh scan."""
    cache_key = f"cinema_scan_{path or 'all'}"
    if not bust:
        cached = _read_cache(cache_key)
        if cached is not None:
            # Always refresh continue_watching from live watch-state
            cached["continue_watching"] = _get_continue_watching(_load_watch_state())
            cached["from_cache"] = True
            return cached

    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
    watch_state = _load_watch_state()

    shows_map = {}
    movies = []
    continue_watching = []

    scan_roots = [resolve_target(path)] if path else ROOTS
    for root in scan_roots:
        if not root or not root.exists():
            continue
        try:
            for dirpath, _, filenames in os.walk(root):
                dir_path = Path(dirpath)
                for f in filenames:
                    ext = Path(f).suffix.lower()
                    if ext in video_exts:
                        full_path = str(dir_path / f).replace("\\", "/")
                        info = _parse_episode_info(f, dir_path.name)
                        ws = watch_state.get(full_path, {})

                        item = {
                            "name": f,
                            "path": full_path,
                            "ext": ext.lstrip("."),
                            "watchState": ws,
                            **info
                        }

                        if ws and not ws.get("completed", False) and ws.get("currentTime", 0) > 10:
                            continue_watching.append(item)

                        if info["is_series"]:
                            show_name = info["show"]
                            if show_name not in shows_map:
                                shows_map[show_name] = {"title": show_name, "seasons": {}}
                            season_name = info["season"]
                            if season_name not in shows_map[show_name]["seasons"]:
                                shows_map[show_name]["seasons"][season_name] = []
                            shows_map[show_name]["seasons"][season_name].append(item)
                        else:
                            movies.append(item)
        except Exception as e:
            print(f"[Cinema Scan Error] {e}")

    # Sort episodes within seasons
    shows_list = []
    for s_title, s_data in shows_map.items():
        formatted_seasons = []
        for season_name, ep_list in s_data["seasons"].items():
            ep_list.sort(key=lambda x: x.get("ep_num", 0))
            formatted_seasons.append({"name": season_name, "episodes": ep_list})
        shows_list.append({"title": s_title, "seasons": formatted_seasons})

    continue_watching.sort(key=lambda x: x.get("watchState", {}).get("updatedAt", 0), reverse=True)

    result = {
        "shows": shows_list,
        "movies": movies[:50],
        "continue_watching": continue_watching[:10],
        "from_cache": False
    }
    _write_cache(cache_key, result)
    return result


def _get_continue_watching(watch_state: dict) -> list:
    """Build continue-watching list from live watch state (not cached)."""
    items = []
    for full_path, ws in watch_state.items():
        if ws and not ws.get("completed", False) and ws.get("currentTime", 0) > 10:
            items.append({"path": full_path, "name": Path(full_path).name, "watchState": ws})
    items.sort(key=lambda x: x.get("watchState", {}).get("updatedAt", 0), reverse=True)
    return items[:10]

@app.get("/api/music/scan")
def scan_music_library(path: str = "", bust: int = 0):
    """Scans and groups audio files into folder playlists. Results cached 30 min.
    Pass ?bust=1 to force a fresh scan and refresh the cache."""
    cache_key = f"music_scan_{path or 'all'}"
    if not bust:
        cached = _read_cache(cache_key)
        if cached is not None:
            cached["from_cache"] = True
            return cached

    audio_exts = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".opus", ".weba"}
    folders_map = {}
    all_tracks = []

    scan_roots = [resolve_target(path)] if path else ROOTS
    for root in scan_roots:
        if not root or not root.exists():
            continue
        try:
            for dirpath, _, filenames in os.walk(root):
                dir_path = Path(dirpath)
                audio_files = [f for f in filenames if Path(f).suffix.lower() in audio_exts]
                if audio_files:
                    folder_name = dir_path.name or "Root Audio"
                    folder_path_str = str(dir_path).replace("\\", "/")
                    track_items = []
                    for f in sorted(audio_files):
                        full_path = str(dir_path / f).replace("\\", "/")
                        t_item = {"name": f, "title": Path(f).stem, "path": full_path, "ext": Path(f).suffix.lstrip(".")}
                        track_items.append(t_item)
                        all_tracks.append(t_item)
                    folders_map[folder_name] = {"folder": folder_name, "path": folder_path_str, "tracks": track_items}
        except Exception as e:
            print(f"[Music Scan Error] {e}")

    result = {"folders": list(folders_map.values()), "total_tracks": len(all_tracks), "from_cache": False}
    _write_cache(cache_key, result)
    return result


@app.get("/api/music/folder")
def music_folder_tracks(path: str):
    """Returns all audio files inside a given folder tree (recursive walk of target directory).
    Used for 'Open folder as playlist' — fast target-scoped scan."""
    audio_exts = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".opus", ".weba"}
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found.")

    tracks = []
    try:
        for dirpath, _, filenames in os.walk(target):
            for f in sorted(filenames, key=lambda x: x.lower()):
                if Path(f).suffix.lower() in audio_exts:
                    full_p = Path(dirpath) / f
                    tracks.append({
                        "name": f,
                        "title": Path(f).stem,
                        "path": str(full_p).replace("\\", "/"),
                        "ext": Path(f).suffix.lstrip(".")
                    })
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"folder": target.name, "path": str(target).replace("\\", "/"), "tracks": tracks}


@app.get("/api/cinema/folder")
def cinema_folder_videos(path: str):
    """Returns all video files inside a given folder tree (recursive walk of target directory).
    Used for 'Open folder' in Cinema Hub — fast target-scoped scan."""
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found.")

    videos = []
    try:
        for dirpath, _, filenames in os.walk(target):
            for f in sorted(filenames, key=lambda x: x.lower()):
                if Path(f).suffix.lower() in video_exts:
                    full_p = Path(dirpath) / f
                    videos.append({
                        "name": f,
                        "title": Path(f).stem,
                        "path": str(full_p).replace("\\", "/"),
                        "ext": Path(f).suffix.lstrip(".")
                    })
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"folder": target.name, "path": str(target).replace("\\", "/"), "videos": videos}


# ==============================================================================
# Sub-App HTML Page Routes
# ==============================================================================

@app.get("/apps/cinema", response_class=HTMLResponse)
def cinema_app(request: Request):
    """Renders Cinema & TV Series Hub sub-app."""
    return _render(request, "cinema_hub.html", {"current_path": "/apps/cinema", "platform": sys.platform})

@app.get("/apps/music", response_class=HTMLResponse)
def music_app(request: Request):
    """Renders Music Hub sub-app."""
    return _render(request, "music_hub.html", {"current_path": "/apps/music", "platform": sys.platform})

@app.get("/apps/gallery", response_class=HTMLResponse)
def gallery_app(request: Request):
    """Renders Photo Gallery sub-app."""
    return _render(request, "gallery_hub.html", {"current_path": "/apps/gallery", "platform": sys.platform})

@app.get("/apps/recent", response_class=HTMLResponse)
def recent_app(request: Request):
    """Renders Starred & Recent sub-app."""
    return _render(request, "recent_hub.html", {"current_path": "/apps/recent", "platform": sys.platform})
