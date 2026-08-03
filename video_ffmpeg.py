"""FFmpeg helpers for AirNode (Phase 6.1, 6.4).

Provides on-demand video transcoding (MKV/Avi → MP4 for phone playback)
and video thumbnail extraction. Both features degrade gracefully when
ffmpeg is not installed — the app keeps working, just without these
enhancements.
"""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from logging_config import get_logger
from paths import get_data_dir

logger = get_logger(__name__)


def find_ffmpeg() -> str | None:
    """Locate the ffmpeg binary (PATH, or alongside the exe in frozen mode)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # Frozen: check next to the AirNode executable
    if getattr(__import__("sys"), "frozen", False):
        app_dir = Path(__import__("sys").executable).resolve().parent
        for candidate in (app_dir / "ffmpeg.exe", app_dir / "ffmpeg"):
            if candidate.exists():
                return str(candidate)
    return None


def find_ffprobe() -> str | None:
    """Locate ffprobe (used for duration/stream info)."""
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    if getattr(__import__("sys"), "frozen", False):
        app_dir = Path(__import__("sys").executable).resolve().parent
        for candidate in (app_dir / "ffprobe.exe", app_dir / "ffprobe"):
            if candidate.exists():
                return str(candidate)
    return None


FFMPEG_AVAILABLE = find_ffmpeg() is not None

# ==============================================================================
# Cache directory
# ==============================================================================

_CACHE_DIR = get_data_dir() / ".airnode_media_cache"


def _ensure_cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _cache_key(path: str, suffix: str) -> Path:
    """Deterministic cache file name for a source path + suffix."""
    digest = hashlib.md5(path.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return _ensure_cache_dir() / f"{digest}{suffix}"


def _cache_fresh(cache_file: Path, source: Path, ttl_seconds: int) -> bool:
    """True if the cache file exists, is newer than source + TTL window."""
    try:
        if not cache_file.exists():
            return False
        return (source.stat().st_mtime + ttl_seconds) < cache_file.stat().st_mtime
    except OSError:
        return False


# ==============================================================================
# Video info (duration, dimensions)
# ==============================================================================

def get_video_info(path: str) -> dict:
    """Return duration and resolution via ffprobe (best-effort)."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return {}
    try:
        cmd = [
            ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
        if result.returncode != 0:
            return {}
        import json
        data = json.loads(result.stdout)
        duration = 0.0
        width = height = None
        fmt = data.get("format", {})
        try:
            duration = float(fmt.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0.0
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                try:
                    width = int(stream.get("width") or 0)
                    height = int(stream.get("height") or 0)
                except (TypeError, ValueError):
                    pass
                if not duration and stream.get("duration"):
                    try:
                        duration = float(stream["duration"])
                    except (TypeError, ValueError):
                        pass
                break
        info = {}
        if duration > 0:
            info["duration"] = round(duration, 1)
        if width and height:
            info["width"] = width
            info["height"] = height
        return info
    except Exception:
        logger.debug("ffprobe failed for %s", path, exc_info=True)
        return {}


# ==============================================================================
# Video thumbnails (6.4)
# ==============================================================================

def _generate_thumbnail_source(source: Path) -> Path | None:
    """Generate a thumbnail next to the source (hidden .airnode_thumb_*) if ffmpeg exists."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    thumb = source.parent / f".airnode_thumb_{source.stem}.jpg"
    if _cache_fresh(thumb, source, ttl_seconds=0) and thumb.stat().st_size > 0:
        return thumb
    try:
        # Grab a frame at ~2 seconds (or the first keyframe if shorter)
        cmd = [
            ffmpeg, "-y", "-v", "quiet",
            "-ss", "2", "-i", str(source),
            "-frames:v", "1", "-vf", "scale='min(320,iw)':-2",
            "-q:v", "4", str(thumb),
        ]
        subprocess.run(cmd, capture_output=True, timeout=20)
        if thumb.exists() and thumb.stat().st_size > 0:
            return thumb
        # Fallback: frame 0
        cmd = [
            ffmpeg, "-y", "-v", "quiet",
            "-i", str(source),
            "-frames:v", "1", "-vf", "scale='min(320,iw)':-2",
            "-q:v", "4", str(thumb),
        ]
        subprocess.run(cmd, capture_output=True, timeout=20)
        if thumb.exists() and thumb.stat().st_size > 0:
            return thumb
    except Exception:
        logger.debug("Thumbnail generation failed for %s", source, exc_info=True)
    return None


def get_video_thumbnail(path: str) -> Path | None:
    """Return a thumbnail image path for a video, or None.

    Tries (in order):
      1. A previously generated hidden .airnode_thumb_*.jpg next to source
      2. A cached thumbnail in the media cache dir
      3. Generates one fresh via ffmpeg
    """
    source = Path(path)
    if not source.exists() or not source.is_file():
        return None

    # 1. Generated alongside source already
    sibling = source.parent / f".airnode_thumb_{source.stem}.jpg"
    if sibling.exists() and sibling.stat().st_size > 0:
        return sibling

    # 2. Cache dir
    cached = _cache_key(str(source), ".jpg")
    if _cache_fresh(cached, source, ttl_seconds=3600) and cached.stat().st_size > 0:
        return cached

    # 3. Generate fresh
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        cmd = [
            ffmpeg, "-y", "-v", "quiet",
            "-ss", "2", "-i", str(source),
            "-frames:v", "1", "-vf", "scale='min(320,iw)':-2",
            "-q:v", "4", str(cached),
        ]
        subprocess.run(cmd, capture_output=True, timeout=20)
        if cached.exists() and cached.stat().st_size > 0:
            return cached
        # Fallback frame 0
        cmd = [
            ffmpeg, "-y", "-v", "quiet",
            "-i", str(source),
            "-frames:v", "1", "-vf", "scale='min(320,iw)':-2",
            "-q:v", "4", str(cached),
        ]
        subprocess.run(cmd, capture_output=True, timeout=20)
        if cached.exists() and cached.stat().st_size > 0:
            return cached
    except Exception:
        logger.debug("Thumbnail cache generation failed for %s", source, exc_info=True)
    return None


# ==============================================================================
# Video transcoding (6.1) — MKV/AVI/MOV → MP4 (H.264/AAC)
# ==============================================================================

_TRANSCODE_EXTENSIONS = {".mkv", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".ts", ".mts", ".m2ts"}

TRANSCODABLE_EXTS = _TRANSCODE_EXTENSIONS


def _transcode_async(source: Path, dest: Path) -> None:
    """Run ffmpeg in a background thread so the request doesn't block."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return
    try:
        cmd = [
            ffmpeg, "-y", "-v", "error",
            "-i", str(source),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(dest),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=3600)
        if result.returncode == 0:
            logger.info("Transcoded %s → %s", source.name, dest.name)
        else:
            logger.warning(
                "Transcode failed for %s: %s",
                source.name,
                result.stderr[-500:] if result.stderr else "unknown error",
            )
            # Clean up partial output
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning("Transcode error for %s: %s", source.name, e)
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass


def start_transcode(path: str) -> dict:
    """Begin transcoding a video to MP4 in the background.

    Returns a dict: {status, task_id, output_path, message}
    """
    source = Path(path)
    if not source.exists() or not source.is_file():
        return {"status": "error", "message": "Source file not found."}

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"status": "unavailable", "message": "FFmpeg is not installed on this device."}

    output = source.with_suffix(".mp4")
    if output.exists() and output.stat().st_size > 0:
        return {
            "status": "exists",
            "message": "A compatible MP4 already exists.",
            "output_path": str(output).replace("\\", "/"),
        }

    # If source is already MP4-compatible, no transcoding needed
    if source.suffix.lower() in (".mp4", ".webm", ".m4v"):
        return {
            "status": "exists",
            "message": "This format plays directly in the browser.",
            "output_path": str(source).replace("\\", "/"),
        }

    threading = __import__("threading")
    thread = threading.Thread(target=_transcode_async, args=(source, output), daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": "Transcoding started in the background.",
        "output_path": str(output).replace("\\", "/"),
    }


def transcode_status(path: str) -> dict:
    """Check whether an MP4 version of the given file exists or is in progress."""
    source = Path(path)
    output = source.with_suffix(".mp4")
    status = {"source": str(source).replace("\\", "/"), "transcoded": False}

    if source.suffix.lower() in (".mp4", ".webm", ".m4v"):
        status["transcoded"] = True
        status["playable_path"] = str(source).replace("\\", "/")
        return status

    if output.exists() and output.stat().st_size > 0:
        # Make sure it's older than the source (i.e. complete, not mid-write partial)
        try:
            if output.stat().st_mtime >= source.stat().st_mtime:
                status["transcoded"] = True
                status["playable_path"] = str(output).replace("\\", "/")
                return status
        except OSError:
            pass

    status["playable_path"] = str(source).replace("\\", "/")
    return status