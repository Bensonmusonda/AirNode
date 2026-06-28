import aiofiles
import os
import sys
import shutil
import string
import ctypes
import mimetypes
import json
import traceback
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
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
    """Validates if the resolved target path lies within allowed root directories."""
    target = target.resolve()
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
        crumbs.append({"label": part, "path": "/".join(parts[:i + 1])})
    return crumbs

def resolve_target(path: str) -> Path | None:
    """Resolves raw path parameters into absolute, OS-specific path instances."""
    if sys.platform == "win32":
        if not path:
            return None
        return Path(path.replace("/", "\\")).resolve()
    else:
        if not path:
            return Path("/")
        return (Path("/") / path).resolve()

def scan_directory(target: Path) -> list[dict]:
    """Scans and retrieves detailed metadata for all file and directory entries inside a path."""
    entries = []
    for item in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        try:
            size = item.stat().st_size if item.is_file() else None
        except PermissionError:
            size = None
        ext = item.suffix.lstrip(".").lower() if item.is_file() else ""
        entries.append({
            "name": item.name,
            "type": "file" if item.is_file() else "directory",
            "size_bytes": size,
            "size_display": format_size(size),
            "path": str(item).replace("\\", "/"),
            "ext": ext,
            "viewable": ext in VIEWABLE_EXTENSIONS,
        })
    return entries

def _render(request: Request, template: str, context: dict):
    """Utility helper to render templates with consistent request contexts."""
    return templates.TemplateResponse(request=request, name=template, context=context)


# ==============================================================================
# HTTP Routes and Endpoints
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Renders the main layout and root drive/directory listing."""
    if sys.platform == "win32":
        entries = [
            {"name": str(r), "type": "directory", "size_display": "", "path": str(r).replace("\\", "/"), "ext": "", "viewable": False}
            for r in ROOTS
        ]
        current_path, breadcrumbs = "/", []
    else:
        target = Path("/")
        entries = scan_directory(target)
        current_path, breadcrumbs = "/", []

    return _render(request, "index.html", {
        "entries": entries,
        "current_path": current_path,
        "breadcrumbs": breadcrumbs,
        "platform": sys.platform,
    })


# === HTMX Directory Browsing ===

@app.get("/browse", response_class=HTMLResponse)
def browse(request: Request, path: str = ""):
    """Handles partial content rendering for HTMX and fallback full-page renders."""
    target = resolve_target(path)
    is_htmx = "HX-Request" in request.headers

    if target is None:
        entries = [
            {"name": str(r), "type": "directory", "size_display": "", "path": str(r).replace("\\", "/"), "ext": "", "viewable": False}
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

    entries = scan_directory(target)
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
def delete_item(request: Request, path: str):
    """Deletes a file or directory securely if it passes validation."""
    target = resolve_target(path)
    if target is None or not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found.")
        
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
            
        # Return a trigger header to tell HTMX to refresh the current directory view
        return HTMLResponse(
            status_code=200, 
            headers={"HX-Trigger": "refresh-directory"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

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

        # 3. Stream binary chunks to disk
        def write_chunk(data_chunk, is_first_chunk):
            mode = "wb" if is_first_chunk else "ab"
            with open(destination, mode) as f:
                f.write(data_chunk)

        is_first = True
        while True:
            chunk = await file.read(1024 * 64)
            if not chunk:
                break
            await run_in_threadpool(write_chunk, chunk, is_first)
            is_first = False

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
def get_properties(path: str):
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
def browse_json(path: str = ""):
    """Returns directory contents as structured JSON for API consumers."""
    target = resolve_target(path)
    if target is None:
        return {"roots": [str(r).replace("\\", "/") for r in ROOTS]}
    if not is_path_allowed(target):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Not found.")
    return {"current_path": str(target).replace("\\", "/"), "entries": scan_directory(target)}