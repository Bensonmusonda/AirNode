import aiofiles
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
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi import UploadFile, Form, File
from fastapi.concurrency import run_in_threadpool
import time


app = FastAPI(title="AirNode")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


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

def _render(request: Request, template: str, context: dict):
    """Utility helper to render templates with consistent request contexts."""
    return templates.TemplateResponse(request=request, name=template, context=context)


# ==============================================================================
# HTTP Routes and Endpoints
# ==============================================================================

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
        if not cleaned_path_str or cleaned_path_str == "undefined":
            target_dir = ROOTS[0] if ROOTS else Path("C:/")
        else:
            target_dir = Path(cleaned_path_str.replace("\\", "/"))

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
# === Streaming File Viewer Endpoint (with HTTP Range request support) ===

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

    mime, _ = mimetypes.guess_type(str(target))
    mime = mime or "application/octet-stream"
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
