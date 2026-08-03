"""Media metadata extraction for AirNode (Phase 6.2, 6.3).

Provides:
  - ID3/audio tag reading (artist, album, title, cover art) via `mutagen`
  - Photo EXIF reading (camera, date, GPS) via Pillow

Both libraries are wrapped in try/except so AirNode keeps working even if
the optional dependency is missing.
"""

import io
import time
from pathlib import Path
from typing import Optional

from logging_config import get_logger

logger = get_logger(__name__)

# ==============================================================================
# Audio tags (6.2) — ID3v2 / Vorbis / MP4
# ==============================================================================

try:
    import mutagen
    from mutagen.id3 import ID3, APIC
    from mutagen.flac import FLAC, Picture
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
    from mutagen.opus import Opus
    _HAS_MUTAGEN = True
except ImportError:
    _HAS_MUTAGEN = False

AUDIO_TAG_EXTS = {".mp3", ".flac", ".m4a", ".ogg", ".opus"}


def _clean(value) -> Optional[str]:
    """Coerce a mutagen tag value to a clean string, or None."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    text = str(value).strip()
    return text or None


def read_audio_tags(path: str) -> dict:
    """Extract artist, album, title, track number and duration from an audio file.

    Returns a dict with keys: title, artist, album, track, duration (seconds).
    Empty fields are omitted. Fully guarded — never raises.
    """
    result: dict = {}
    if not _HAS_MUTAGEN:
        return result

    p = Path(path)
    if p.suffix.lower() not in AUDIO_TAG_EXTS:
        return result

    try:
        mtime = p.stat().st_mtime if p.exists() else 0.0
        cache_key = f"audio_tags:{p}"
        from db import kv_get, kv_set
        cached = kv_get(cache_key)
        if cached:
            import json as _json
            try:
                data = _json.loads(cached)
                if data.get("mtime") == mtime and data.get("tags"):
                    return data["tags"]
            except Exception:
                pass

        tags: dict = {}
        ext = p.suffix.lower()

        if ext == ".mp3":
            try:
                audio = ID3(path)
                tags["title"] = _clean(audio.get("TIT2"))
                tags["artist"] = _clean(audio.get("TPE1"))
                tags["album"] = _clean(audio.get("TALB"))
                trck = audio.get("TRCK")
                if trck:
                    num = str(trck).split("/")[0].strip()
                    if num.isdigit():
                        tags["track"] = int(num)
            except Exception:
                pass
        elif ext == ".flac":
            try:
                audio = FLAC(path)
                tags["title"] = _clean(audio.get("title"))
                tags["artist"] = _clean(audio.get("artist"))
                tags["album"] = _clean(audio.get("album"))
                trck = _clean(audio.get("tracknumber"))
                if trck and trck.isdigit():
                    tags["track"] = int(trck)
            except Exception:
                pass
        elif ext == ".m4a":
            try:
                audio = MP4(path)
                tags["title"] = _clean(audio.get("\xa9nam"))
                tags["artist"] = _clean(audio.get("\xa9ART"))
                tags["album"] = _clean(audio.get("\xa9alb"))
                trck = audio.get("trkn")
                if trck and isinstance(trck, list) and trck:
                    try:
                        tags["track"] = int(trck[0][0])
                    except (ValueError, TypeError, IndexError):
                        pass
            except Exception:
                pass
        elif ext in (".ogg", ".opus"):
            try:
                audio = (Opus(path) if ext == ".opus" else OggVorbis(path))
                tags["title"] = _clean(audio.get("title"))
                tags["artist"] = _clean(audio.get("artist"))
                tags["album"] = _clean(audio.get("album"))
                trck = _clean(audio.get("tracknumber"))
                if trck and trck.isdigit():
                    tags["track"] = int(trck)
            except Exception:
                pass

        # Duration (best-effort, may be 0)
        try:
            if ext == ".mp3":
                audio = ID3(path)
                tags["duration"] = round(audio.info.length, 1) if audio.info else 0
            elif ext == ".flac":
                audio = FLAC(path)
                tags["duration"] = round(audio.info.length, 1) if audio.info else 0
            elif ext == ".m4a":
                audio = MP4(path)
                tags["duration"] = round(audio.info.length, 1) if audio.info else 0
            elif ext in (".ogg", ".opus"):
                audio = (Opus(path) if ext == ".opus" else OggVorbis(path))
                tags["duration"] = round(audio.info.length, 1) if audio.info else 0
        except Exception:
            pass
        if "duration" in tags and tags["duration"] <= 0:
            del tags["duration"]

        if tags:
            import json as _json
            kv_set(cache_key, _json.dumps({"mtime": mtime, "tags": tags}), ttl_seconds=86400)
        return tags
    except Exception:
        logger.debug("Failed to read audio tags for %s", path, exc_info=True)
        return result


def extract_cover_art(path: str) -> Optional[bytes]:
    """Return embedded cover art (JPEG/PNG bytes) or None.

    Supports MP3 (APIC), FLAC (Picture) and M4A (covr). Returns the first
    image found, preferring large front-cover images.
    """
    if not _HAS_MUTAGEN:
        return None

    p = Path(path)
    if not p.exists() or p.suffix.lower() not in AUDIO_TAG_EXTS:
        return None

    try:
        ext = p.suffix.lower()
        if ext == ".mp3":
            audio = ID3(path)
            apics = audio.getall("APIC")
            if apics:
                # Prefer front cover (type 3), then any image
                apics.sort(key=lambda a: (a.type != 3, len(a.data or b"")))
                if apics[0].data:
                    return bytes(apics[0].data)
        elif ext == ".flac":
            audio = FLAC(path)
            pics = audio.pictures
            if pics:
                pics.sort(key=lambda pic: (pic.type != 3, len(pic.data or b"")))
                return bytes(pics[0].data)
        elif ext == ".m4a":
            audio = MP4(path)
            covers = audio.get("covr", [])
            if covers:
                return bytes(covers[0])
    except Exception:
        logger.debug("Failed to read cover art for %s", path, exc_info=True)
    return None


# ==============================================================================
# Photo EXIF (6.3) — Pillow
# ==============================================================================

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".heic", ".heif", ".bmp"}


def _to_float(value) -> Optional[float]:
    """EXIF rationals come back as (num, den) tuples."""
    try:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            num, den = value
            if not den:
                return None
            return float(num) / float(den)
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _format_gps(coord, ref: str) -> Optional[float]:
    """Convert (degrees, minutes, seconds) EXIF GPS tuple to decimal degrees."""
    try:
        d = _to_float(coord[0]) if isinstance(coord, (tuple, list)) and len(coord) >= 1 else None
        m = _to_float(coord[1]) if isinstance(coord, (tuple, list)) and len(coord) >= 2 else None
        s = _to_float(coord[2]) if isinstance(coord, (tuple, list)) and len(coord) >= 3 else None
        if d is None:
            return None
        deg = d + (m or 0) / 60.0 + (s or 0) / 3600.0
        if ref and ref.upper() in ("S", "W"):
            deg = -deg
        return round(deg, 6)
    except (TypeError, ValueError):
        return None


def read_image_exif(path: str) -> dict:
    """Extract camera model, date taken, dimensions and GPS coordinates.

    Returns a dict with keys: camera, captured_at, width, height, gps_lat, gps_lon,
    orientation, iso, focal_length, exposure, f_number. Missing fields omitted.
    """
    result: dict = {}
    if not _HAS_PIL:
        return result

    p = Path(path)
    if p.suffix.lower() not in IMAGE_EXTS:
        return result

    try:
        mtime = p.stat().st_mtime if p.exists() else 0.0
        cache_key = f"exif:{p}"
        from db import kv_get, kv_set
        cached = kv_get(cache_key)
        if cached:
            import json as _json
            try:
                data = _json.loads(cached)
                if data.get("mtime") == mtime and data.get("exif"):
                    return data["exif"]
            except Exception:
                pass

        exif_data: dict = {}
        try:
            with Image.open(path) as img:
                exif_data["width"] = img.width
                exif_data["height"] = img.height

                exif_raw = img.getexif()
                if exif_raw:
                    gps_info_raw = exif_raw.get_ifd(0x8825) if hasattr(exif_raw, "get_ifd") else {}
                    exif_map = {TAGS.get(k, k): v for k, v in exif_raw.items()}

                    # Camera
                    make = str(exif_map.get("Make") or "").strip()
                    model = str(exif_map.get("Model") or "").strip()
                    if make and model:
                        exif_data["camera"] = f"{make} {model}".strip()
                    elif model:
                        exif_data["camera"] = model

                    # Date taken
                    date_original = exif_map.get("DateTimeOriginal") or exif_map.get("DateTime")
                    if date_original:
                        date_str = str(date_original).strip()
                        try:
                            parsed = time.strptime(date_str[:19], "%Y:%m:%d %H:%M:%S")
                            exif_data["captured_at"] = time.strftime("%Y-%m-%d %H:%M:%S", parsed)
                        except ValueError:
                            exif_data["captured_at_raw"] = date_str

                    # Orientation (1–8)
                    if "Orientation" in exif_map:
                        try:
                            exif_data["orientation"] = int(exif_map["Orientation"])
                        except (TypeError, ValueError):
                            pass

                    # Lens / exposure info
                    if "ISOSpeedRatings" in exif_map:
                        try:
                            iso_val = exif_map["ISOSpeedRatings"]
                            if isinstance(iso_val, (tuple, list)):
                                iso_val = iso_val[0]
                            exif_data["iso"] = int(iso_val)
                        except (TypeError, ValueError):
                            pass
                    if "FNumber" in exif_map:
                        fnum = _to_float(exif_map["FNumber"])
                        if fnum:
                            exif_data["f_number"] = f"f/{fnum:.1f}"
                    if "ExposureTime" in exif_map:
                        et = _to_float(exif_map["ExposureTime"])
                        if et and et > 0:
                            exif_data["exposure"] = f"1/{round(1/et)}s" if et < 1 else f"{et:.1f}s"
                    if "FocalLength" in exif_map:
                        fl = _to_float(exif_map["FocalLength"])
                        if fl:
                            exif_data["focal_length"] = f"{fl:.0f}mm"

                    # GPS coordinates
                    if gps_info_raw:
                        gps_map = {GPSTAGS.get(k, k): v for k, v in gps_info_raw.items()}
                        lat = _format_gps(gps_map.get("GPSLatitude"), gps_map.get("GPSLatitudeRef"))
                        lon = _format_gps(gps_map.get("GPSLongitude"), gps_map.get("GPSLongitudeRef"))
                        if lat is not None:
                            exif_data["gps_lat"] = lat
                        if lon is not None:
                            exif_data["gps_lon"] = lon
        except Exception:
            logger.debug("Failed to read EXIF from %s", path, exc_info=True)

        if exif_data:
            import json as _json
            kv_set(cache_key, _json.dumps({"mtime": mtime, "exif": exif_data}), ttl_seconds=86400)
            return exif_data
    except Exception:
        logger.debug("EXIF read failed for %s", path, exc_info=True)
    return result


def rotate_image_bytes(data: bytes, orientation: int) -> bytes:
    """Apply EXIF orientation so the image displays upright in the browser."""
    if not _HAS_PIL or orientation in (1, 0):
        return data
    try:
        with Image.open(io.BytesIO(data)) as img:
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
            out = io.BytesIO()
            fmt = img.format or "JPEG"
            if fmt == "PNG":
                img.save(out, format="PNG")
            else:
                img = img.convert("RGB")
                img.save(out, format="JPEG", quality=88)
            return out.getvalue()
    except Exception:
        return data