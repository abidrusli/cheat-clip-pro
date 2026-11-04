import asyncio
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from backend.config import (
    EXPORTS_DIR,
    TEMP_DIR,
    UPLOADS_DIR,
    FONTS_DIR,
    detect_speaker_face_box,
    extract_clip_frame,
    get_video_file_metadata,
    is_valid_mp4,
    logger,
)

router = APIRouter(tags=["Media"])


MAX_VIDEO_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024   # 4 GB
MAX_AUDIO_UPLOAD_BYTES = 100 * 1024 * 1024        # 100 MB
MAX_SFX_UPLOAD_BYTES = 50 * 1024 * 1024           # 50 MB
MAX_IMAGE_UPLOAD_BYTES = 25 * 1024 * 1024         # 25 MB
MAX_FONT_UPLOAD_BYTES = 50 * 1024 * 1024          # 50 MB

# Audio formats that FFmpeg can decode. Keep this list broad so files picked from
# Android/iOS (for example WhatsApp .opus notes) are accepted as well.
AUDIO_EXTENSIONS = {
    ".mp3", ".mp2", ".wav", ".m4a", ".m4b", ".mp4", ".aac", ".ogg", ".oga",
    ".opus", ".flac", ".wma", ".aiff", ".aif", ".amr", ".3gp", ".weba",
    ".mka", ".caf", ".ape", ".ac3", ".eac3",
}

AUDIO_MIME_TO_EXT = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp2": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/vnd.wave": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/aacp": ".aac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/webm": ".weba",
    "audio/x-ms-wma": ".wma",
    "audio/aiff": ".aiff",
    "audio/x-aiff": ".aiff",
    "audio/amr": ".amr",
    "audio/3gpp": ".3gp",
    "audio/x-matroska": ".mka",
    "audio/x-caf": ".caf",
    "audio/x-ape": ".ape",
    "audio/ac3": ".ac3",
    "audio/eac3": ".eac3",
}

AUDIO_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".mp2": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".m4b": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".wma": "audio/x-ms-wma",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".amr": "audio/amr",
    ".3gp": "audio/3gpp",
    ".weba": "audio/webm",
    ".mka": "audio/x-matroska",
    ".caf": "audio/x-caf",
    ".ape": "audio/x-ape",
    ".ac3": "audio/ac3",
    ".eac3": "audio/eac3",
}


def _resolve_audio_extension(filename: Optional[str], content_type: Optional[str]) -> Optional[str]:
    """Returns a safe audio extension, inferring it from the MIME type when the
    browser/WebView sends a filename without one (common on Android)."""
    name = (filename or "").strip()
    ext = os.path.splitext(name)[1].lower()
    if ext in AUDIO_EXTENSIONS:
        return ext

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in AUDIO_MIME_TO_EXT:
        return AUDIO_MIME_TO_EXT[mime]

    # Some Android file providers report a generic audio MIME type but still
    # include a usable extension (for example audio/x-matroska + .mka).
    if mime.startswith("audio/"):
        if re.fullmatch(r"\.[a-z0-9]{1,6}", ext):
            return ext
        return ".mp3"

    return None


def _audio_media_type(filename: str) -> str:
    return AUDIO_MEDIA_TYPES.get(os.path.splitext(filename)[1].lower(), "application/octet-stream")


def _is_safe_path(target_path: Path) -> bool:
    """Ensures the resolved file path is strictly located within allowed media directories."""
    try:
        resolved = target_path.resolve()
        allowed_roots = [UPLOADS_DIR.resolve(), TEMP_DIR.resolve(), EXPORTS_DIR.resolve(), FONTS_DIR.resolve()]
        return any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots)
    except Exception:
        return False


async def _save_uploaded_file_chunked(file: UploadFile, save_path: Path, max_bytes: int) -> int:
    """
    Streams upload content in 1MB chunks to disk while enforcing a strict maximum size limit
    to prevent memory exhaustion (OOM) and disk flood attacks.
    """
    total_written = 0
    chunk_size = 1024 * 1024  # 1 MB
    try:
        with open(save_path, "wb") as f:
            while chunk := await file.read(chunk_size):
                total_written += len(chunk)
                if total_written > max_bytes:
                    f.close()
                    if save_path.exists():
                        save_path.unlink()
                    limit_mb = round(max_bytes / (1024 * 1024))
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file exceeds the maximum allowed size limit of {limit_mb} MB."
                    )
                f.write(chunk)
        return total_written
    except HTTPException:
        raise
    except Exception as e:
        if save_path.exists():
            try:
                save_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")


@router.post("/api/upload-video")
async def upload_video(
    file: UploadFile = File(...),
    client_duration: Optional[float] = Form(None),
    client_width: Optional[int] = Form(None),
    client_height: Optional[int] = Form(None),
    original_filename: Optional[str] = Form(None),
):
    """
    Handles local video or browser-extracted audio uploads (.mp4, .mov, .mkv, .webm, .avi, .wav, .mp3, etc.).
    Extracts metadata and saves to uploads folder.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    display_filename = original_filename or file.filename
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".wmv", ".wav", ".mp3", ".m4a", ".ogg", ".aac", ".flac"]
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported media format. Allowed: {', '.join(allowed)}")
    
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', display_filename)
    unique_id = f"upload_{uuid.uuid4().hex[:10]}"
    unique_name = f"{unique_id}_{clean_name}"
    save_path = UPLOADS_DIR / unique_name
    
    try:
        bytes_written = await _save_uploaded_file_chunked(file, save_path, MAX_VIDEO_UPLOAD_BYTES)
        meta = await asyncio.to_thread(get_video_file_metadata, save_path)
        
        final_duration = meta.get("duration") or (client_duration if client_duration and client_duration > 0 else 0.0)
        final_width = (client_width if client_width and client_width > 0 else meta.get("width")) or 1920
        final_height = (client_height if client_height and client_height > 0 else meta.get("height")) or 1080
        
        logger.info(f"Uploaded media '{display_filename}' -> saved as '{unique_name}' ({final_duration}s, {final_width}x{final_height}, {bytes_written} bytes)")
        
        return {
            "success": True,
            "video_id": unique_id,
            "filename": display_filename,
            "saved_name": unique_name,
            "file_path": str(save_path),
            "video_url": f"/api/video/{unique_name}",
            "duration": final_duration,
            "width": final_width,
            "height": final_height,
            "has_audio": True,
            "size_bytes": bytes_written
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process video upload: {str(e)}")


def _find_video_file_on_disk(file_name: str) -> Optional[Path]:
    import urllib.parse
    clean_name = urllib.parse.unquote(os.path.basename(file_name.split("?")[0])).strip()
    
    # Check direct paths
    for base in [UPLOADS_DIR, TEMP_DIR, EXPORTS_DIR]:
        candidate = base / clean_name
        if candidate.exists() and candidate.is_file() and _is_safe_path(candidate):
            return candidate

    # Search directory listings without regex/glob pitfalls
    all_files: list[Path] = []
    for d in [UPLOADS_DIR, TEMP_DIR, EXPORTS_DIR]:
        if d.exists():
            all_files.extend([f for f in d.iterdir() if f.is_file() and _is_safe_path(f)])

    clean_lower = clean_name.lower()
    
    # 1. Exact case-insensitive match
    for f in all_files:
        if f.name.lower() == clean_lower:
            return f

    # 2. Match without extension
    stem_lower = os.path.splitext(clean_lower)[0]
    for f in all_files:
        if f.stem.lower() == stem_lower or f.stem.lower() == clean_lower:
            return f

    # 3. Match Google Drive or Upload ID substring
    drive_match = re.search(r'([a-zA-Z0-9_-]{20,})', clean_name)
    if drive_match:
        fid = drive_match.group(1)
        for f in all_files:
            if fid in f.name:
                return f

    upload_match = re.search(r'(upload_[a-zA-Z0-9]{6,})', clean_name)
    if upload_match:
        uid = upload_match.group(1)
        for f in all_files:
            if uid in f.name:
                return f

    # 4. Containment matching
    for f in all_files:
        if clean_lower in f.name.lower() or f.stem.lower() in clean_lower:
            return f

    return None


@router.get("/api/video/{file_name:path}")
def get_video_file(file_name: str, request: Request):
    """
    Streams local video files with HTTP byte ranges support (HTTP 206 Partial Content)
    for smooth seeking, immediate playback start, and previewing without loading the whole file.
    """
    file_path = _find_video_file_on_disk(file_name)
    if not file_path or not file_path.exists() or not _is_safe_path(file_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    file_size = file_path.stat().st_size
    ext = os.path.splitext(file_path.name)[1].lower()
    media_type = "video/webm" if ext == ".webm" else "video/quicktime" if ext == ".mov" else "video/x-matroska" if ext == ".mkv" else "video/mp4"

    range_header = request.headers.get("range")
    if not range_header:
        # Full file streaming response with Accept-Ranges
        def iter_full():
            with open(file_path, "rb") as f:
                while chunk := f.read(1024 * 512):
                    yield chunk

        return StreamingResponse(
            iter_full(),
            status_code=200,
            media_type=media_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'inline; filename="{file_path.name}"'
            }
        )

    # Parse Range: bytes=start-end
    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        return Response(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)

    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

    if start >= file_size or end >= file_size or start > end:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"}
        )

    content_length = end - start + 1

    def iter_range():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = content_length
            while bytes_left > 0:
                chunk_size = min(1024 * 512, bytes_left)
                data = f.read(chunk_size)
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    return StreamingResponse(
        iter_range(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Disposition": f'inline; filename="{file_path.name}"'
        }
    )


@router.post("/api/upload-bgm")
async def upload_bgm(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = _resolve_audio_extension(file.filename, file.content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Please use MP3, WAV, M4A, AAC, OGG/OPUS, or FLAC.",
        )

    base_name = os.path.splitext(os.path.basename(file.filename))[0] or "bgm"
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', base_name) + ext
    unique_name = f"bgm_{uuid.uuid4().hex[:8]}_{clean_name}"
    save_path = UPLOADS_DIR / unique_name

    try:
        bytes_written = await _save_uploaded_file_chunked(file, save_path, MAX_AUDIO_UPLOAD_BYTES)
        if bytes_written <= 0:
            if save_path.exists():
                save_path.unlink()
            raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
        logger.info(f"Uploaded BGM '{file.filename}' -> '{unique_name}' ({bytes_written} bytes)")
        return {
            "success": True,
            "filename": file.filename,
            "saved_name": unique_name,
            "file_path": str(save_path),
            "url": f"/api/audio/{unique_name}",
            "content_type": _audio_media_type(unique_name),
            "size_bytes": bytes_written
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload BGM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _stream_audio_file(file_path: Path, request: Request) -> Response:
    """Streams audio with byte-range support so the <audio> preview can seek."""
    file_size = file_path.stat().st_size
    media_type = _audio_media_type(file_path.name)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{file_path.name}"',
    }

    range_header = request.headers.get("range")
    if not range_header:
        def iter_full():
            with open(file_path, "rb") as f:
                while chunk := f.read(1024 * 512):
                    yield chunk

        headers["Content-Length"] = str(file_size)
        return StreamingResponse(iter_full(), status_code=200, media_type=media_type, headers=headers)

    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        return Response(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                        headers={"Content-Range": f"bytes */{file_size}"})

    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
    if start >= file_size or end >= file_size or start > end:
        return Response(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                        headers={"Content-Range": f"bytes */{file_size}"})

    content_length = end - start + 1

    def iter_range():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = content_length
            while bytes_left > 0:
                data = f.read(min(1024 * 512, bytes_left))
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    headers["Content-Length"] = str(content_length)
    return StreamingResponse(iter_range(), status_code=206, media_type=media_type, headers=headers)


@router.get("/api/audio/{file_name}")
def get_audio_file(file_name: str, request: Request):
    clean_name = os.path.basename(file_name)
    file_path = UPLOADS_DIR / clean_name
    if not file_path.exists() or not _is_safe_path(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return _stream_audio_file(file_path, request)


@router.post("/api/upload-sfx")
async def upload_hook_sfx(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = _resolve_audio_extension(file.filename, file.content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Please use MP3, WAV, M4A, AAC, OGG/OPUS, or FLAC.",
        )

    base_name = os.path.splitext(os.path.basename(file.filename))[0] or "sfx"
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', base_name) + ext
    unique_name = f"sfx_{uuid.uuid4().hex[:8]}_{clean_name}"
    save_path = UPLOADS_DIR / unique_name

    try:
        bytes_written = await _save_uploaded_file_chunked(file, save_path, MAX_SFX_UPLOAD_BYTES)
        if bytes_written <= 0:
            if save_path.exists():
                save_path.unlink()
            raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
        return {
            "success": True,
            "filename": file.filename,
            "saved_name": unique_name,
            "file_path": str(save_path),
            "url": f"/api/audio/{unique_name}",
            "content_type": _audio_media_type(unique_name),
            "size_bytes": bytes_written
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload Hook SFX: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/upload-watermark")
async def upload_watermark(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = [".png", ".jpg", ".jpeg", ".webp", ".svg"]
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported image format. Allowed: {', '.join(allowed)}")
    
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
    unique_name = f"wm_{uuid.uuid4().hex[:8]}_{clean_name}"
    save_path = UPLOADS_DIR / unique_name
    
    try:
        bytes_written = await _save_uploaded_file_chunked(file, save_path, MAX_IMAGE_UPLOAD_BYTES)
        return {
            "success": True,
            "filename": file.filename,
            "saved_name": unique_name,
            "file_path": str(save_path),
            "url": f"/api/watermark/{unique_name}",
            "size_bytes": bytes_written
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload watermark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/watermark/{file_name}")
def get_watermark_file(file_name: str):
    clean_name = os.path.basename(file_name)
    file_path = UPLOADS_DIR / clean_name
    if not file_path.exists() or not _is_safe_path(file_path):
        raise HTTPException(status_code=404, detail="Watermark file not found")
    media_type = "image/png" if clean_name.endswith(".png") else "image/jpeg" if (clean_name.endswith(".jpg") or clean_name.endswith(".jpeg")) else "image/webp"
    return FileResponse(file_path, media_type=media_type, filename=clean_name)


@router.get("/api/clip-frame")
async def get_clip_frame(video_id: str, timestamp: float = 0.0, video_url: Optional[str] = None):
    """
    Returns an extracted real video frame at timestamp for the real video preview.
    Guarantees returning a real video frame, never a promotional thumbnail.
    """
    try:
        frame_path = await asyncio.to_thread(extract_clip_frame, video_url or "", video_id, timestamp)
        if frame_path and os.path.exists(frame_path):
            return FileResponse(frame_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        logger.warning(f"Failed to serve extracted frame for {video_id}: {e}")

    raise HTTPException(status_code=404, detail="Real video frame could not be extracted yet")


@router.get("/api/detect-face")
async def detect_face(
    video_id: str,
    timestamp: float = 0.0,
    video_url: Optional[str] = None,
    facecam_position: Optional[str] = "auto",
    streamer_preset: Optional[str] = "none"
):
    """
    Detects speaker face coordinates (cx, cy, w, h) on the video at timestamp.
    Returns normalized coordinates and the frame URL.
    """
    is_streamer = (streamer_preset or "none") in ["split_top_cam", "pip_corner"]
    default_cx = 0.85 if is_streamer else 0.5
    default_cy = 0.78 if is_streamer else 0.35
    default_res = {
        "found": False,
        "cx": default_cx,
        "cy": default_cy,
        "w": 0.22,
        "h": 0.25,
        "frame_url": f"/api/clip-frame?video_id={video_id}&timestamp={timestamp}"
    }
    try:
        # First try to extract or get the cached frame
        frame_path = await asyncio.to_thread(extract_clip_frame, video_url or "", video_id, timestamp)
        if frame_path and os.path.exists(frame_path):
            box = await asyncio.to_thread(
                detect_speaker_face_box,
                frame_path,
                facecam_position or "auto",
                streamer_preset or "none"
            )
            box["frame_url"] = f"/api/clip-frame?video_id={video_id}&timestamp={timestamp}"
            return box

        # If frame extract didn't complete, check local candidates
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', video_id)
        local_candidates = list(TEMP_DIR.glob(f"*{safe_id}*.mp4")) + list(EXPORTS_DIR.glob(f"*{safe_id}*.mp4"))
        for candidate in local_candidates:
            if candidate.exists() and candidate.stat().st_size > 10000 and "slice_" not in candidate.name and is_valid_mp4(candidate):
                box = await asyncio.to_thread(
                    detect_speaker_face_box,
                    str(candidate),
                    facecam_position or "auto",
                    streamer_preset or "none"
                )
                box["frame_url"] = f"/api/clip-frame?video_id={video_id}&timestamp={timestamp}"
                return box
    except Exception as e:
        logger.warning(f"Face detection API error: {e}")

    return default_res


MAX_FACECAM_VIDEO_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_VOICEOVER_BYTES = 200 * 1024 * 1024           # 200 MB


@router.post("/api/upload-facecam")
async def upload_facecam(file: UploadFile = File(...)):
    """Uploads the user's own facecam/avatar (video or image) used as a clip overlay."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = os.path.splitext(file.filename)[1].lower()
    video_exts = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"]
    image_exts = [".png", ".jpg", ".jpeg", ".webp"]
    if ext in video_exts:
        media_kind = "video"
        max_bytes = MAX_FACECAM_VIDEO_BYTES
    elif ext in image_exts:
        media_kind = "image"
        max_bytes = MAX_IMAGE_UPLOAD_BYTES
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported facecam format. Allowed: {', '.join(video_exts + image_exts)}",
        )

    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
    unique_name = f"facecam_{uuid.uuid4().hex[:8]}_{clean_name}"
    save_path = UPLOADS_DIR / unique_name
    try:
        bytes_written = await _save_uploaded_file_chunked(file, save_path, max_bytes)
        logger.info(f"Uploaded facecam '{file.filename}' -> '{unique_name}' ({media_kind}, {bytes_written} bytes)")
        return {
            "success": True,
            "filename": file.filename,
            "saved_name": unique_name,
            "file_path": str(save_path),
            "url": f"/api/facecam/{unique_name}",
            "media_type": media_kind,
            "size_bytes": bytes_written,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload facecam: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/facecam/{file_name}")
def get_facecam_file(file_name: str):
    clean_name = os.path.basename(file_name)
    file_path = UPLOADS_DIR / clean_name
    if not file_path.exists() or not _is_safe_path(file_path):
        raise HTTPException(status_code=404, detail="Facecam file not found")
    ext = os.path.splitext(clean_name)[1].lower()
    if ext in [".png", ".jpg", ".jpeg", ".webp"]:
        media_type = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
    elif ext == ".webm":
        media_type = "video/webm"
    elif ext == ".mov":
        media_type = "video/quicktime"
    elif ext == ".mkv":
        media_type = "video/x-matroska"
    else:
        media_type = "video/mp4"
    return FileResponse(file_path, media_type=media_type, filename=clean_name)


@router.post("/api/upload-voiceover")
async def upload_voiceover(file: UploadFile = File(...)):
    """Uploads a user voice-over narration audio track to mix into the rendered clip."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = _resolve_audio_extension(file.filename, file.content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Please use MP3, WAV, M4A, AAC, OGG/OPUS, or FLAC.",
        )

    base_name = os.path.splitext(os.path.basename(file.filename))[0] or "voiceover"
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', base_name) + ext
    unique_name = f"vo_{uuid.uuid4().hex[:8]}_{clean_name}"
    save_path = UPLOADS_DIR / unique_name
    try:
        bytes_written = await _save_uploaded_file_chunked(file, save_path, MAX_VOICEOVER_BYTES)
        if bytes_written <= 0:
            if save_path.exists():
                save_path.unlink()
            raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
        logger.info(f"Uploaded voiceover '{file.filename}' -> '{unique_name}' ({bytes_written} bytes)")
        return {
            "success": True,
            "filename": file.filename,
            "saved_name": unique_name,
            "file_path": str(save_path),
            "url": f"/api/audio/{unique_name}",
            "content_type": _audio_media_type(unique_name),
            "size_bytes": bytes_written,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload voiceover: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/upload-font")
async def upload_font(file: UploadFile = File(...)):
    """
    Handles custom font file uploads (.ttf, .otf, .woff, .woff2).
    Saves to fonts directory so preview and libass / ffmpeg can immediately render with it.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = [".ttf", ".otf", ".woff", ".woff2"]
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported font format. Allowed: {', '.join(allowed)}")

    clean_stem = re.sub(r'[^a-zA-Z0-9_\-\s]', '_', os.path.splitext(file.filename)[0]).strip()
    if not clean_stem:
        clean_stem = f"CustomFont_{uuid.uuid4().hex[:6]}"
    
    saved_filename = f"{clean_stem}{ext}"
    save_path = FONTS_DIR / saved_filename

    try:
        bytes_written = await _save_uploaded_file_chunked(file, save_path, MAX_FONT_UPLOAD_BYTES)
        
        # Extract font family name using PIL ImageFont
        font_family = clean_stem
        try:
            from PIL import ImageFont
            loaded_f = ImageFont.truetype(str(save_path), 24)
            names = loaded_f.getname()
            if names and names[0]:
                font_family = str(names[0]).strip()
        except Exception as font_err:
            logger.info(f"Could not read font table name ({font_err}); using stem '{clean_stem}'")

        logger.info(f"Uploaded custom font: '{file.filename}' -> saved as '{saved_filename}' (Family: '{font_family}', {bytes_written} bytes)")

        return {
            "success": True,
            "font_name": font_family,
            "filename": saved_filename,
            "url": f"/api/font-file/{saved_filename}",
            "size_bytes": bytes_written
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload font: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save custom font: {str(e)}")


@router.get("/api/fonts")
def list_available_fonts():
    """
    Returns the complete list of built-in and uploaded custom fonts.
    """
    default_builtin = [
        "Outfit",
        "Montserrat",
        "Inter",
        "Impact",
        "Bebas Neue",
        "Anton",
        "Poppins",
        "Arial Black",
    ]
    fonts_map = {}
    for name in default_builtin:
        fonts_map[name.lower()] = {
            "name": name,
            "is_custom": False,
            "filename": None,
            "url": None
        }

    # Discover fonts on disk
    if FONTS_DIR.exists():
        for f in FONTS_DIR.iterdir():
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in [".ttf", ".otf", ".woff", ".woff2"]:
                continue
            # Skip emoji helper fonts
            if f.name.lower() in ["seguiemj.ttf", "notocoloremoji.ttf"]:
                continue

            font_family = f.stem
            try:
                from PIL import ImageFont
                loaded = ImageFont.truetype(str(f), 24)
                names = loaded.getname()
                if names and names[0]:
                    font_family = str(names[0]).strip()
            except Exception:
                pass

            key = font_family.lower()
            is_builtin = key in fonts_map and not fonts_map[key]["is_custom"]
            fonts_map[key] = {
                "name": font_family,
                "is_custom": not is_builtin,
                "filename": f.name,
                "url": f"/api/font-file/{f.name}"
            }

    return {"success": True, "fonts": list(fonts_map.values())}


@router.get("/api/font-file/{file_name}")
def get_font_file(file_name: str):
    """
    Serves font binary with correct MIME type for frontend FontFace and CSS loading.
    """
    clean_name = os.path.basename(file_name)
    file_path = FONTS_DIR / clean_name
    if not file_path.exists() or not _is_safe_path(file_path):
        raise HTTPException(status_code=404, detail="Font file not found")

    ext = os.path.splitext(clean_name)[1].lower()
    media_type = "font/woff2" if ext == ".woff2" else "font/woff" if ext == ".woff" else "font/otf" if ext == ".otf" else "font/ttf"
    return FileResponse(file_path, media_type=media_type, filename=clean_name)
