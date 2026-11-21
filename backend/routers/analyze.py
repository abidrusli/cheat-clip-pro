import asyncio
import json
import logging
import os
import re
import time
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from pathlib import Path

from backend.config import (
    TEMP_DIR,
    UPLOADS_DIR,
    compute_audio_energy_heatmap,
    get_video_file_metadata,
    logger,
    transcribe_local_video_file,
)
from backend.schemas.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    HeatmapPoint,
    TranscriptLine,
    TranslatedTranscript,
    VideoAnalysis,
    ViralClip,
)
from backend.services.ai_service import (
    KNOWN_FLASH_MODELS,
    get_flash_models_for_key,
    list_available_gemini_models,
)
from backend.services.gdrive_service import (
    download_google_drive_video,
    is_google_drive_url,
)
from backend.services.social_service import (
    detect_social_platform,
    download_social_video,
    get_social_platform_label,
)
from backend.services.system_service import (
    is_server_environment,
    is_update_allowed,
)
from backend.services.youtube_service import (
    fetch_transcript,
    fetch_video_metadata,
    get_supadata_keys,
    get_supadata_usage_data,
)
from backend.utils.heatmap import get_average_heatmap_value
from backend.utils.proxy import get_proxy_url
from backend.utils.sse import _sse
from backend.utils.text import (
    detect_transcript_language,
    extract_video_id,
    lowercase_hashtags_in_string,
    parse_manual_subtitles,
    sanitize_first_person_title,
)


# Larger chunks mean far fewer Gemini requests. On the Free Tier each model is
# limited to 20 generateContent requests/day, so translating a long video in
# 150-line slices could exhaust the quota in a single run.
TRANSLATION_CHUNK_SIZE = 800
TRANSLATION_TIMEOUT_SEC = 180.0


def _format_gemini_error(exc: Exception, model_name: str) -> Tuple[bool, str]:
    """Return (is_quota_error, pesan Bahasa Indonesia) untuk error Gemini."""
    text = str(exc)
    lowered = text.lower()
    is_quota = (
        "429" in text
        or "resource_exhausted" in lowered
        or "quota" in lowered
        or "exceeded your current quota" in lowered
    )
    if not is_quota:
        return False, f"Model {model_name} gagal: {text}"

    retry_note = ""
    match = re.search(r"retryDelay['\"]?\s*:\s*['\"](\d+(?:\.\d+)?)s", text)
    if match:
        seconds = int(float(match.group(1)))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        parts = []
        if hours:
            parts.append(f"{hours} jam")
        if minutes:
            parts.append(f"{minutes} menit")
        if secs and not hours:
            parts.append(f"{secs} detik")
        retry_note = f" Coba lagi dalam {', '.join(parts)}."
    else:
        plain = re.search(r"Please retry in ([^'\"}\n]+)", text)
        if plain:
            retry_note = f" Coba lagi dalam {plain.group(1).strip()}."

    message = (
        f"Kuota harian Gemini gratis untuk model {model_name} sudah habis "
        f"(20 request/hari per model).{retry_note} "
        "Gunakan API key/project lain atau aktifkan billing, lalu coba lagi."
    )
    return True, message


def _resolve_output_language(
    requested: Optional[str],
    source_code: str,
    source_name: str,
) -> Tuple[str, str]:
    """Resolve the requested output language into a language code and display name."""
    target = (requested or "source").strip().lower()
    if target in ("", "source", "original", "auto", "none"):
        return source_code, source_name
    if target in ("id", "in", "indonesia", "indonesian", "bahasa", "bahasa indonesia"):
        return "id", "Indonesian"
    if target in ("en", "eng", "english"):
        return "en", "English"
    # Unknown values fall back to the source language instead of silently
    # producing a mixture of languages.
    logger.warning(f"Unknown output_language '{requested}'. Falling back to source language {source_name}.")
    return source_code, source_name


def _parse_translation_json(raw_text: str) -> List[dict]:
    """Parse a translation response that may be wrapped in markdown fences."""
    if not raw_text:
        return []

    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```[a-zA-Z]*\s*", "", clean_text)
        clean_text = re.sub(r"\s*```$", "", clean_text)
    clean_text = clean_text.strip()

    candidates = [clean_text, re.sub(r",\s*([\]}])", r"\1", clean_text)]
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue

        if isinstance(data, dict):
            data = (
                data.get("lines")
                or data.get("translations")
                or data.get("translated_lines")
                or []
            )
        if not isinstance(data, list):
            continue

        parsed = []
        for item in data:
            if not isinstance(item, dict):
                continue
            index = item.get("index", item.get("i"))
            text = item.get("text", item.get("translation"))
            if index is None or text is None:
                continue
            try:
                parsed.append({"index": int(index), "text": str(text).strip()})
            except (TypeError, ValueError):
                continue
        if parsed:
            return parsed
    return []


def _extract_translation_lines(response) -> List[dict]:
    """Extract index/text pairs from a structured Gemini response."""
    parsed = getattr(response, "parsed", None)
    lines = None
    if parsed is not None:
        lines = getattr(parsed, "lines", None)
        if lines is None and isinstance(parsed, dict):
            lines = parsed.get("lines")

    if lines:
        extracted = []
        for item in lines:
            if isinstance(item, dict):
                index = item.get("index")
                text = item.get("text")
            else:
                index = getattr(item, "index", None)
                text = getattr(item, "text", None)
            if index is None or text is None:
                continue
            try:
                extracted.append({"index": int(index), "text": str(text).strip()})
            except (TypeError, ValueError):
                continue
        if extracted:
            return extracted

    return _parse_translation_json(getattr(response, "text", "") or "")


def _translate_transcript_chunk(
    client,
    models_to_try: List[str],
    chunk: List[dict],
    source_lang_name: str,
    target_lang_name: str,
) -> List[str]:
    """Translate one chunk of subtitle lines while preserving indices and timestamps."""
    payload = [
        {"index": i, "text": str(line.get("text", "")).strip()}
        for i, line in enumerate(chunk)
    ]
    prompt = (
        f"You are a professional subtitle translator for short-form viral videos.\n"
        f"Translate every subtitle line from {source_lang_name} to natural, conversational {target_lang_name}.\n\n"
        f"RULES:\n"
        f"- Translate the meaning naturally, as a human editor would for TikTok, Reels, and Shorts subtitles.\n"
        f"- Keep each input line as a separate output line with the SAME index.\n"
        f"- Do NOT merge, split, omit, reorder, or add lines.\n"
        f"- Do NOT include timestamps, notes, explanations, or surrounding quotation marks.\n"
        f"- Preserve names, numbers, brands, URLs, hashtags, emojis, and proper nouns.\n"
        f"- If a line is already in {target_lang_name}, keep it unchanged.\n"
        f"- Keep translations concise and easy to read on screen.\n"
        f"- Return ONLY valid JSON matching this schema: {{\"lines\":[{{\"index\":0,\"text\":\"...\"}}]}}.\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )

    meaningful_indices = [
        i for i, line in enumerate(chunk)
        if any(ch.isalnum() for ch in str(line.get("text", "")))
    ]
    last_error = None

    for model_name in models_to_try[:3]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=TranslatedTranscript,
                        temperature=0.1,
                        max_output_tokens=16384,
                    ),
                )
                translated = _extract_translation_lines(response)
                mapping = {}
                for item in translated:
                    index = item.get("index")
                    if isinstance(index, int) and 0 <= index < len(chunk):
                        text = str(item.get("text", "")).strip()
                        if text:
                            mapping[index] = text

                # Every meaningful line must be translated. Missing lines would
                # leave English text inside an Indonesian-subtitled video.
                covered = sum(1 for i in meaningful_indices if i in mapping)
                if meaningful_indices and covered < len(meaningful_indices):
                    raise ValueError(
                        f"incomplete translation ({covered}/{len(meaningful_indices)} lines)"
                    )
                if not meaningful_indices and not mapping:
                    return [str(line.get("text", "")) for line in chunk]

                return [
                    mapping.get(i, str(chunk[i].get("text", "")))
                    for i in range(len(chunk))
                ]
            except Exception as e:
                last_error = e
                error_text = str(e)
                is_quota, friendly = _format_gemini_error(e, model_name)
                is_not_found = "404" in error_text or "NOT_FOUND" in error_text.upper()
                logger.warning(
                    f"Translation with {model_name} failed (attempt {attempt + 1}/2): "
                    f"{friendly if is_quota else error_text}"
                )
                if is_quota:
                    raise RuntimeError(friendly) from e
                if is_not_found:
                    # Retired/unsupported model for this key. Do not waste a
                    # second attempt; move straight to the next model.
                    break
                if attempt == 0:
                    time.sleep(1.2)

    raise RuntimeError(
        f"Gagal menerjemahkan dengan model Gemini yang tersedia: {last_error}"
    )


def _format_parsed_dict(data: dict, channel: str, lang_code: str) -> dict:
    raw_clips = data.get("clips") or []
    formatted_clips = []
    for c in raw_clips:
        if not isinstance(c, dict):
            continue
        title = sanitize_first_person_title(str(c.get('title', '')), channel, lang=lang_code)
        title_sug = sanitize_first_person_title(str(c.get('title_suggestion', '')), channel, lang=lang_code)
        formatted_clips.append({
            "title": title,
            "start_time": float(c.get('start_time', 0.0) or 0.0),
            "end_time": float(c.get('end_time', 0.0) or 0.0),
            "hook_time": float(c.get('hook_time')) if c.get('hook_time') is not None else None,
            "virality_score": int(c.get('virality_score', 0) or 0),
            "key_quotes": c.get('key_quotes') if isinstance(c.get('key_quotes'), list) else [],
            "title_suggestion": title_sug,
            "caption_suggestion": str(c.get('caption_suggestion', '') or ''),
            "hashtag_suggestion": str(c.get('hashtag_suggestion', '') or ''),
        })
    return {
        "summary": str(data.get("summary", "") or ""),
        "clips": formatted_clips
    }


def parse_lenient_json_analysis(raw_text: str, channel: str = "", lang_code: str = "en") -> Optional[dict]:
    """Robust parser that extracts and repairs structured analysis even if truncated, unescaped, or containing trailing commas."""
    if not raw_text or not raw_text.strip():
        return None
    
    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```[a-zA-Z]*\n?", "", clean_text)
        clean_text = re.sub(r"\n?```$", "", clean_text)
    clean_text = clean_text.strip()

    # 1. Standard json parse
    try:
        data = json.loads(clean_text)
        if isinstance(data, dict):
            return _format_parsed_dict(data, channel, lang_code)
    except Exception:
        pass

    # 2. Fix trailing commas (e.g. [...,])
    try:
        no_trailing_commas = re.sub(r',\s*([\]}])', r'\1', clean_text)
        data = json.loads(no_trailing_commas)
        if isinstance(data, dict):
            return _format_parsed_dict(data, channel, lang_code)
    except Exception:
        pass

    # 3. Truncated JSON repair (recovers clips when output was cut off mid-response)
    try:
        last_brace_idx = clean_text.rfind("}")
        if last_brace_idx != -1:
            truncated_candidate = clean_text[:last_brace_idx + 1]
            if '"clips"' in truncated_candidate:
                if not truncated_candidate.endswith("]}"):
                    if truncated_candidate.endswith("]"):
                        truncated_candidate += "}"
                    else:
                        truncated_candidate += "\n]}"
                truncated_candidate = re.sub(r',\s*([\]}])', r'\1', truncated_candidate)
                data = json.loads(truncated_candidate)
                if isinstance(data, dict):
                    return _format_parsed_dict(data, channel, lang_code)
    except Exception:
        pass

    # 4. Lenient Regex-based Clip Extraction (recovers individual clips even with corrupted JSON syntax)
    try:
        clips_list = []
        summary_match = re.search(r'"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_text)
        summary = summary_match.group(1).encode().decode('unicode_escape') if summary_match else ""

        raw_clip_blocks = re.findall(r'\{[^{}]*?"(?:title|start_time)"[^{}]*?\}', clean_text, re.DOTALL)
        for block in raw_clip_blocks:
            try:
                clip_obj = json.loads(block)
            except Exception:
                title_m = re.search(r'"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', block)
                start_m = re.search(r'"start_time"\s*:\s*([\d\.]+)', block)
                end_m = re.search(r'"end_time"\s*:\s*([\d\.]+)', block)
                hook_m = re.search(r'"hook_time"\s*:\s*([\d\.]+)', block)
                score_m = re.search(r'"virality_score"\s*:\s*(\d+)', block)
                sug_m = re.search(r'"title_suggestion"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', block)
                cap_m = re.search(r'"caption_suggestion"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', block)
                tag_m = re.search(r'"hashtag_suggestion"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', block)
                quotes_m = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', block)

                clip_obj = {
                    "title": title_m.group(1) if title_m else "",
                    "start_time": float(start_m.group(1)) if start_m else 0.0,
                    "end_time": float(end_m.group(1)) if end_m else 0.0,
                    "hook_time": float(hook_m.group(1)) if hook_m else None,
                    "virality_score": int(score_m.group(1)) if score_m else 75,
                    "key_quotes": quotes_m[:2] if quotes_m else [],
                    "title_suggestion": sug_m.group(1) if sug_m else "",
                    "caption_suggestion": cap_m.group(1) if cap_m else "",
                    "hashtag_suggestion": tag_m.group(1) if tag_m else "",
                }

            if clip_obj.get("start_time", 0.0) or clip_obj.get("end_time", 0.0) or clip_obj.get("title"):
                clips_list.append(clip_obj)

        if clips_list:
            return _format_parsed_dict({"summary": summary, "clips": clips_list}, channel, lang_code)
    except Exception as e:
        logger.warning(f"Lenient regex parsing error: {e}")

    return None


router = APIRouter(tags=["Analyze"])


@router.get("/api/health")
def health_check(refresh: bool = False):
    is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    keys = get_supadata_keys()
    proxy = get_proxy_url()
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    supadata_info = get_supadata_usage_data(force=refresh) if keys else {
        "total_keys": 0,
        "total_limit": 0,
        "total_used": 0,
        "total_remaining": 0,
        "usage_percent": 0.0,
        "active_keys": 0,
        "exhausted_keys": 0,
        "keys_detail": [],
        "status": "not_configured"
    }
    return {
        "status": "ok",
        "message": "SINYALABIDNET KLIPER PRO API is active",
        "is_vercel": is_vercel,
        "is_server": is_server_environment(),
        "allow_app_updates": is_update_allowed(),
        "proxy_configured": bool(proxy),
        "gemini_env_configured": has_gemini,
        "supadata_keys_count": len(keys),
        "supadata": supadata_info
    }


@router.get("/api/supadata-usage")
def supadata_usage_endpoint(refresh: bool = False):
    """Returns real-time usage and remaining credit quota across all configured Supadata API keys."""
    return get_supadata_usage_data(force=refresh)


@router.get("/api/models")
def list_available_models(api_key: str = ""):
    """Fetches list of available Gemini models using the user's API key, prioritizing Flash models (newest first)."""
    models = list_available_gemini_models(api_key)
    return {"models": models}


@router.post("/api/analyze")
async def analyze_video(request: AnalyzeRequest):
    """Stream real-time progress via Server-Sent Events, then deliver the final result."""

    async def stream():
        gemini_key = (request.api_key or os.environ.get("GEMINI_API_KEY") or '').strip()
        is_mock = gemini_key.lower() == "mock"

        if not gemini_key:
            yield _sse({"error": "Gemini API Key is required. Enter it in the web interface.", "status": 400})
            return

        # ── Step 1: Detect Source Type & Extract Metadata ───────────────────
        req_clean = request.url.strip()
        is_uploaded = False
        is_gdrive = is_google_drive_url(req_clean)
        social_platform = detect_social_platform(req_clean)
        is_social = social_platform is not None
        social_title = ""
        social_channel = ""
        uploaded_file_path: Optional[Path] = None

        if is_gdrive:
            yield _sse({
                "step": 1,
                "step_progress": 10,
                "overall_progress": 5,
                "stage": "Connecting to Google Drive",
                "detail": "Resolving Google Drive sharing link & preparing download...",
                "message": "Connecting to Google Drive..."
            })
            loop = asyncio.get_running_loop()
            gdrive_queue: asyncio.Queue = asyncio.Queue()

            def gdrive_progress(stage: str, detail: str, step_pct: int = 30):
                loop.call_soon_threadsafe(gdrive_queue.put_nowait, {
                    "step": 1,
                    "step_progress": step_pct,
                    "overall_progress": min(22, 5 + int(step_pct * 0.17)),
                    "stage": stage,
                    "detail": detail,
                    "message": detail
                })

            try:
                task = asyncio.create_task(
                    asyncio.to_thread(download_google_drive_video, req_clean, gdrive_progress)
                )
                while not task.done():
                    try:
                        evt = await asyncio.wait_for(gdrive_queue.get(), timeout=0.2)
                        yield _sse(evt)
                    except asyncio.TimeoutError:
                        pass
                while not gdrive_queue.empty():
                    yield _sse(gdrive_queue.get_nowait())

                uploaded_file_path = await task
                is_uploaded = True
            except Exception as e:
                yield _sse({"error": f"Failed to fetch video from Google Drive: {str(e)}", "status": 400})
                return
        elif is_social:
            platform_label = get_social_platform_label(social_platform or "")
            yield _sse({
                "step": 1,
                "step_progress": 10,
                "overall_progress": 5,
                "stage": f"Connecting to {platform_label}",
                "detail": f"Resolving the public {platform_label} video link & preparing download...",
                "message": f"Connecting to {platform_label}..."
            })
            loop = asyncio.get_running_loop()
            social_queue: asyncio.Queue = asyncio.Queue()

            def social_progress(stage: str, detail: str, step_pct: int = 30):
                loop.call_soon_threadsafe(social_queue.put_nowait, {
                    "step": 1,
                    "step_progress": step_pct,
                    "overall_progress": min(22, 5 + int(step_pct * 0.17)),
                    "stage": stage,
                    "detail": detail,
                    "message": detail
                })

            try:
                task = asyncio.create_task(
                    asyncio.to_thread(download_social_video, req_clean, social_progress)
                )
                while not task.done():
                    try:
                        evt = await asyncio.wait_for(social_queue.get(), timeout=0.2)
                        yield _sse(evt)
                    except asyncio.TimeoutError:
                        pass
                while not social_queue.empty():
                    yield _sse(social_queue.get_nowait())

                social_result = await task
                uploaded_file_path = social_result.path
                social_title = social_result.title
                social_channel = social_result.uploader or platform_label
                is_uploaded = True
            except Exception as e:
                yield _sse({
                    "error": f"Failed to download {platform_label} video: {str(e)}",
                    "status": 400
                })
                return
        elif req_clean.startswith("upload_") or req_clean.startswith("/api/video/") or req_clean.startswith("file://") or os.path.exists(req_clean):
            is_uploaded = True
        elif (UPLOADS_DIR / os.path.basename(req_clean.split("?")[0])).exists():
            is_uploaded = True
        else:
            matches = list(UPLOADS_DIR.glob(f"*{req_clean}*"))
            if matches:
                is_uploaded = True

        if is_uploaded:
            if uploaded_file_path is None:
                if os.path.exists(req_clean):
                    uploaded_file_path = Path(req_clean)
                elif (UPLOADS_DIR / os.path.basename(req_clean.split("?")[0])).exists():
                    uploaded_file_path = UPLOADS_DIR / os.path.basename(req_clean.split("?")[0])
                elif (TEMP_DIR / os.path.basename(req_clean.split("?")[0])).exists():
                    uploaded_file_path = TEMP_DIR / os.path.basename(req_clean.split("?")[0])
                else:
                    matches = list(UPLOADS_DIR.glob(f"*{req_clean}*"))
                    if matches:
                        uploaded_file_path = matches[0]
                    else:
                        yield _sse({"error": "Uploaded video file not found on disk. Please upload again.", "status": 404})
                        return

            video_id = uploaded_file_path.stem
            canonical_url = req_clean if (is_gdrive or is_social) else f"/api/video/{uploaded_file_path.name}"
            video_url = f"/api/video/{uploaded_file_path.name}"
            source_type = "gdrive" if is_gdrive else ("social" if is_social else "upload")

            yield _sse({
                "step": 1,
                "step_progress": 30,
                "overall_progress": 8,
                "stage": "Inspecting Video File",
                "detail": f"Reading streams & container metadata from {uploaded_file_path.name}...",
                "message": f"Inspecting video file: {uploaded_file_path.name}..."
            })

            try:
                metadata = await asyncio.to_thread(get_video_file_metadata, uploaded_file_path)
                if is_social and social_title:
                    title = social_title
                else:
                    title = metadata.get("title") or (uploaded_file_path.stem.replace("gdrive_", "GDrive: ") if is_gdrive else uploaded_file_path.stem)
                channel = social_channel or ("Google Drive" if is_gdrive else "Local Upload")
                duration = metadata.get("duration", 0.0)
                is_live = False
                live_status = "not_live"
                yield _sse({
                    "step": 1,
                    "step_progress": 100,
                    "overall_progress": 25,
                    "stage": "Video Verified",
                    "detail": f"Loaded video \"{title[:45]}\" ({int(duration)}s, {metadata.get('width')}x{metadata.get('height')})",
                    "message": f"Loaded video — \"{title[:45]}\" ({int(duration)}s)"
                })
            except Exception as e:
                yield _sse({"error": f"Failed to probe uploaded video metadata: {str(e)}", "status": 500})
                return

            logger.info(f"Local video loaded: title='{title}', duration={duration}s, path={uploaded_file_path}")

            # ── Step 2: Heatmap via acoustic energy ──────────────────────────
            yield _sse({
                "step": 2,
                "step_progress": 40,
                "overall_progress": 35,
                "stage": "Computing Acoustic Heatmap",
                "detail": "Analyzing audio energy envelope & speech intensity peaks...",
                "message": "Computing audio engagement curve..."
            })
            try:
                heatmap = await asyncio.to_thread(compute_audio_energy_heatmap, uploaded_file_path, duration)
                yield _sse({
                    "step": 2,
                    "step_progress": 100,
                    "overall_progress": 50,
                    "stage": "Acoustic Peaks Decoded",
                    "detail": f"Acoustic engagement heatmap parsed — {len(heatmap)} audience interest data points generated.",
                    "message": f"Acoustic energy heatmap loaded ({len(heatmap)} points)."
                })
            except Exception as e:
                logger.warning(f"Heatmap calculation error: {e}")
                heatmap = []
                yield _sse({
                    "step": 2,
                    "step_progress": 100,
                    "overall_progress": 50,
                    "stage": "Dialogue Fallback",
                    "detail": "Proceeding with full dialogue transcript analysis.",
                    "message": "Proceeding with speech transcription..."
                })

            # ── Step 3: Speech Recognition via Whisper AI ───────────────────
            if request.subtitles:
                yield _sse({
                    "step": 3,
                    "step_progress": 30,
                    "overall_progress": 55,
                    "stage": "Parsing Subtitles",
                    "detail": "Parsing custom SRT/TXT subtitle timestamps...",
                    "message": "Parsing manual subtitles..."
                })
                try:
                    transcript_lines = parse_manual_subtitles(request.subtitles, duration)
                    if not transcript_lines:
                        raise Exception("Custom subtitles parsed into empty array.")
                    yield _sse({
                        "step": 3,
                        "step_progress": 100,
                        "overall_progress": 70,
                        "stage": "Subtitles Ready",
                        "detail": f"Custom subtitles parsed — {len(transcript_lines)} timestamped lines loaded.",
                        "message": f"Custom subtitles parsed — {len(transcript_lines)} lines loaded successfully."
                    })
                except Exception as e:
                    yield _sse({"error": f"Failed to parse manual subtitles: {str(e)}", "status": 400})
                    return
            else:
                loop = asyncio.get_running_loop()
                progress_queue = asyncio.Queue()

                def whisper_progress(stage: str, detail: str, step_pct: int = 30):
                    loop.call_soon_threadsafe(progress_queue.put_nowait, {
                        "step": 3,
                        "step_progress": step_pct,
                        "overall_progress": min(68, 50 + int(step_pct * 0.2)),
                        "stage": stage,
                        "detail": detail,
                        "message": detail
                    })

                yield _sse({
                    "step": 3,
                    "step_progress": 25,
                    "overall_progress": 55,
                    "stage": "Transcribing with Whisper",
                    "detail": "Running OpenAI Whisper neural speech model on video audio track...",
                    "message": "Transcribing video dialogue with Whisper AI..."
                })

                try:
                    task = asyncio.create_task(
                        asyncio.to_thread(transcribe_local_video_file, uploaded_file_path, whisper_progress)
                    )
                    while not task.done():
                        try:
                            evt = await asyncio.wait_for(progress_queue.get(), timeout=0.2)
                            yield _sse(evt)
                        except asyncio.TimeoutError:
                            pass

                    while not progress_queue.empty():
                        yield _sse(progress_queue.get_nowait())

                    transcript_lines = await task
                    if not transcript_lines:
                        if is_mock:
                            transcript_lines = [
                                {"text": "Hello and welcome to this video.",            "start":  0.0, "duration": 3.0},
                                {"text": "Today we are looking at how this app works.",  "start":  3.0, "duration": 4.0},
                                {"text": "It finds viral hotspots and highlights them.",  "start":  7.0, "duration": 4.0},
                                {"text": "This works locally on any uploaded file.",     "start": 11.0, "duration": 3.0},
                            ]
                        else:
                            yield _sse({
                                "error": "No spoken words were detected in this video file. Ensure the video contains clear audible speech.",
                                "status": 400
                            })
                            return

                    yield _sse({
                        "step": 3,
                        "step_progress": 100,
                        "overall_progress": 70,
                        "stage": "Dialogue Transcribed",
                        "detail": f"Whisper speech-to-text complete — {len(transcript_lines)} timestamped dialogue sentences ready.",
                        "message": f"Whisper transcribed {len(transcript_lines)} dialogue segments successfully."
                    })
                except Exception as e:
                    if is_mock:
                        transcript_lines = [
                            {"text": "Sample speech from uploaded mock video.", "start": 0.0, "duration": 4.0},
                            {"text": "Highlighting viral moments automatically.", "start": 4.0, "duration": 5.0}
                        ]
                    else:
                        yield _sse({"error": f"Whisper transcription failed: {str(e)}", "status": 500})
                        return

        else:
            # ── YouTube extraction path ──────────────────────────────────────
            source_type = "youtube"
            video_url = None
            video_id = extract_video_id(request.url)
            if not video_id:
                if not is_mock:
                    yield _sse({"error": "Invalid YouTube URL or file reference. Please check and try again.", "status": 400})
                    return
                video_id = "dQw4w9WgXcQ"

            canonical_url = f"https://www.youtube.com/watch?v={video_id}"

            yield _sse({
                "step": 1,
                "step_progress": 30,
                "overall_progress": 8,
                "stage": "Connecting to YouTube",
                "detail": "Connecting to YouTube & fetching video metadata...",
                "message": "Connecting to YouTube — fetching video title and duration..."
            })

            channel = ""
            try:
                metadata = await asyncio.to_thread(fetch_video_metadata, canonical_url, request.proxy, request.cookies)
                title    = metadata["title"]
                channel  = metadata.get("channel", "")
                duration = metadata["duration"]
                heatmap  = metadata.get("heatmap") or []
                is_live  = metadata.get("is_live", False)
                live_status = metadata.get("live_status", "not_live")
                yield _sse({
                    "step": 1,
                    "step_progress": 100,
                    "overall_progress": 25,
                    "stage": "Video Verified",
                    "detail": f"Loaded metadata for \"{title[:45]}\" ({int(duration)}s)",
                    "message": f"Connected — \"{title[:45]}\" ({int(duration)}s)"
                })
            except Exception as e:
                if is_mock:
                    title = "Mock YouTube Video"
                    channel = "SinyalAbidnet Kliper Pro"
                    duration = 212.0
                    heatmap = []
                    is_live = False
                    live_status = "not_live"
                    yield _sse({
                        "step": 1,
                        "step_progress": 100,
                        "overall_progress": 25,
                        "stage": "Video Verified",
                        "detail": "Loaded mock video metadata (212s)",
                        "message": "Mock video metadata loaded"
                    })
                else:
                    msg = e.detail if isinstance(e, HTTPException) else str(e)
                    yield _sse({"error": f"Failed to fetch video details: {msg}", "status": 500})
                    return

            logger.info(f"Metadata fetched: title='{title}', duration={duration}s, heatmap_pts={len(heatmap)}")

            # ── Step 2: Heatmap ──────────────────────────────────────────────────
            yield _sse({
                "step": 2,
                "step_progress": 40,
                "overall_progress": 35,
                "stage": "Scraping Retention",
                "detail": "Extracting viewer replay telemetry and retention curve...",
                "message": "Scraping player viewer retention curve..."
            })
            if heatmap:
                yield _sse({
                    "step": 2,
                    "step_progress": 100,
                    "overall_progress": 50,
                    "stage": "Retention Decoded",
                    "detail": f"Viewer retention heatmap loaded — {len(heatmap)} audience interest data points parsed.",
                    "message": f"Viewer retention heatmap loaded — {len(heatmap)} data points scraped."
                })
            else:
                yield _sse({
                    "step": 2,
                    "step_progress": 100,
                    "overall_progress": 50,
                    "stage": "Dialogue Fallback",
                    "detail": "No heatmap curve available — relying on full transcript dialogue analysis.",
                    "message": "No heatmap available for this video — will rely on transcript content analysis."
                })

            # ── Step 3: Transcript ───────────────────────────────────────────────
            if request.subtitles:
                yield _sse({
                    "step": 3,
                    "step_progress": 30,
                    "overall_progress": 55,
                    "stage": "Parsing Subtitles",
                    "detail": "Parsing custom SRT/TXT subtitle timestamps...",
                    "message": "Parsing manual subtitles..."
                })
                try:
                    transcript_lines = parse_manual_subtitles(request.subtitles, duration)
                    if not transcript_lines:
                        raise Exception("Custom subtitles parsed into empty array.")
                    yield _sse({
                        "step": 3,
                        "step_progress": 100,
                        "overall_progress": 70,
                        "stage": "Subtitles Ready",
                        "detail": f"Custom subtitles parsed — {len(transcript_lines)} timestamped lines loaded.",
                        "message": f"Custom subtitles parsed — {len(transcript_lines)} lines loaded successfully."
                    })
                except Exception as e:
                    yield _sse({"error": f"Failed to parse manual subtitles: {str(e)}", "status": 400})
                    return
            else:
                loop = asyncio.get_running_loop()
                progress_queue = asyncio.Queue()

                def progress_callback(stage: str, detail: str, step_pct: int = 30):
                    loop.call_soon_threadsafe(progress_queue.put_nowait, {
                        "step": 3,
                        "step_progress": step_pct,
                        "overall_progress": min(68, 50 + int(step_pct * 0.2)),
                        "stage": stage,
                        "detail": detail,
                        "message": detail
                    })

                # Initial stage event
                yield _sse({
                    "step": 3,
                    "step_progress": 25,
                    "overall_progress": 55,
                    "stage": "Fetching Subtitles",
                    "detail": "Initializing multi-tier subtitle extraction pipeline...",
                    "message": "Initializing multi-tier subtitle extraction pipeline..."
                })

                try:
                    task = asyncio.create_task(
                        asyncio.to_thread(fetch_transcript, video_id, request.proxy, progress_callback, request.cookies)
                    )

                    while not task.done():
                        try:
                            evt = await asyncio.wait_for(progress_queue.get(), timeout=0.2)
                            yield _sse(evt)
                        except asyncio.TimeoutError:
                            pass

                    while not progress_queue.empty():
                        yield _sse(progress_queue.get_nowait())

                    transcript_lines = await task
                    yield _sse({
                        "step": 3,
                        "step_progress": 100,
                        "overall_progress": 70,
                        "stage": "Subtitles Ready",
                        "detail": f"Subtitles loaded — {len(transcript_lines)} dialogue sentences with timestamps ready.",
                        "message": f"Subtitles loaded — {len(transcript_lines)} lines parsed successfully."
                    })
                except Exception as e:
                    if is_mock:
                        transcript_lines = [
                            {"text": "Hello and welcome to this video.",            "start":  0.0, "duration": 3.0},
                            {"text": "Today we are looking at how this app works.",  "start":  3.0, "duration": 4.0},
                            {"text": "It finds viral hotspots and highlights them.",  "start":  7.0, "duration": 4.0},
                            {"text": "Most people think it's magic.",               "start": 11.0, "duration": 3.0},
                            {"text": "But it uses YouTube player heatmaps.",         "start": 14.0, "duration": 4.0},
                            {"text": "And processes them with Gemini AI models.",    "start": 18.0, "duration": 4.0},
                            {"text": "This is changing how editors crop videos.",    "start": 22.0, "duration": 5.0},
                            {"text": "If you want to grow on TikTok, try it.",      "start": 27.0, "duration": 5.0},
                            {"text": "We will explore the code next.",               "start": 32.0, "duration": 3.0},
                        ]
                        yield _sse({
                            "step": 3,
                            "step_progress": 100,
                            "overall_progress": 70,
                            "stage": "Subtitles Ready",
                            "detail": "Mock mode — 9 sample dialogue lines loaded.",
                            "message": "Mock mode — using sample transcript."
                        })
                    else:
                        if is_live or live_status in ('is_live', 'is_upcoming', 'post_live'):
                            yield _sse({
                                "error": (
                                    "No subtitles could be retrieved because this video is currently live, "
                                    "upcoming, or recently completed (post-live processing). Subtitles are only "
                                    "available once the live stream ends and YouTube finishes processing the video. "
                                    "You can upload custom subtitles manually to analyze this video."
                                ),
                                "status": 400
                            })
                        else:
                            msg = e.detail if isinstance(e, HTTPException) else str(e)
                            yield _sse({"error": msg, "status": 400})
                        return

        # Estimate duration from transcript if missing
        if duration == 0.0 and transcript_lines:
            last = transcript_lines[-1]
            duration = last.get("start", 0.0) + last.get("duration", 0.0)

        # Slice transcript based on custom search range if provided
        start_bound = 0.0
        end_bound = duration
        if request.range_start is not None or request.range_end is not None:
            start_bound = request.range_start if request.range_start is not None else 0.0
            end_bound = request.range_end if request.range_end is not None else duration

            if start_bound < 0.0:
                start_bound = 0.0
            if end_bound > duration:
                end_bound = duration

            if start_bound >= end_bound:
                yield _sse({"error": "Invalid search range: start time must be less than end time.", "status": 400})
                return

            filtered_lines = []
            for line in transcript_lines:
                ls = line.get("start", 0.0)
                le = ls + line.get("duration", 0.0)
                if max(ls, start_bound) < min(le, end_bound):
                    filtered_lines.append(line)
            
            transcript_lines = filtered_lines
            if not transcript_lines:
                yield _sse({"error": f"No subtitles found in the specified range {start_bound}s to {end_bound}s.", "status": 400})
                return
            
            duration = end_bound - start_bound
            logger.info(f"Filtered transcript to custom range: {start_bound}s to {end_bound}s (duration: {duration}s)")

        # Enrich transcript with heatmap engagement scores
        enriched_transcript = []
        for line in transcript_lines:
            ls   = line.get("start", 0.0)
            ld   = line.get("duration", 0.0)
            le   = ls + ld
            score = get_average_heatmap_value(ls, le, heatmap)
            enriched_transcript.append({
                "start":      round(ls, 2),
                "end":        round(le, 2),
                "text":       line.get("text", ""),
                "engagement": round(score, 3)
            })

        # ── Mock short-circuit ───────────────────────────────────────────────
        if is_mock:
            mock_stages = [
                ("Context Assembly", "Aligning 9 transcript dialogue lines with retention telemetry...", 30, 78),
                ("Viral Hook & Curiosity Detection", "Scanning transcript dialogue for viral hooks & curiosity gaps...", 65, 88),
                ("Virality Scoring & Selection", "Calculating virality coefficients and formatting clip candidates...", 92, 95),
            ]
            for s_name, s_detail, s_prog, o_prog in mock_stages:
                yield _sse({
                    "step": 4,
                    "step_progress": s_prog,
                    "overall_progress": o_prog,
                    "stage": s_name,
                    "detail": s_detail,
                    "model": "gemini-2.5-flash (Mock)",
                    "message": f"Mock AI ({s_name}): {s_detail}"
                })
                await asyncio.sleep(0.7)

            mock_clips = [
                ViralClip(title="Finding hotspots using heatmaps",  start_time=11.0, end_time=22.0, hook_time=14.0, virality_score=95,
                          key_quotes=["Uses YouTube player heatmaps.", "Processes using Gemini AI."],
                          transcript="Most people think it's magic. But it uses YouTube player heatmaps.",
                          title_suggestion="Unlock Video Virality Secrets",
                          caption_suggestion="Stop guessing what works! Here's how to use heatmaps to find viral hotspots in seconds. 🔥",
                          hashtag_suggestion="#viralclips #videoediting #heatmaps #aitools"),
                ViralClip(title="Grow on TikTok or Reels",          start_time=22.0, end_time=32.0, hook_time=27.0, virality_score=88,
                          key_quotes=["Changing how editors crop videos.", "If you want to grow on TikTok, try it."],
                          transcript="This is changing how editors crop videos. If you want to grow on TikTok, try it.",
                          title_suggestion="The Ultimate TikTok Growth Hack",
                          caption_suggestion="Want to scale your TikTok views? This tool will revolutionize your workflow. 🚀",
                          hashtag_suggestion="#tiktokgrowth #reels #shorts #editingtips"),
                ViralClip(title="Introductory overview of the tool", start_time=0.0,  end_time=11.0, hook_time=3.0, virality_score=72,
                          key_quotes=["Hello and welcome.", "Finds viral hotspots."],
                          transcript="Hello and welcome. It finds viral hotspots and highlights them.",
                          title_suggestion="Meet SinyalAbidnet Kliper Pro AI",
                          caption_suggestion="Say hello to your new AI co-editor. Find the absolute best parts of any video instantly.",
                          hashtag_suggestion="#cheatclippro #aiediting #growthmindset"),
            ]
            mock_heatmap = [
                HeatmapPoint(start_time=i*10.0, end_time=(i+1)*10.0,
                             value=0.2 + (0.6 if i in [2,5,8,12,16] else 0.1))
                for i in range(20)
            ] if not heatmap else [
                HeatmapPoint(start_time=float(pt.get('start_time',0.0)),
                             end_time=float(pt.get('end_time',0.0)),
                             value=float(pt.get('value',0.0)))
                for pt in heatmap
            ]
            result = AnalyzeResponse(
                video_id=video_id, title=title, channel=channel, duration=duration or 200.0,
                heatmap=mock_heatmap,
                summary="Mock analysis: this video explains how SINYALABIDNET KLIPER PRO works. #aitools #videoediting #productivity",
                clips=mock_clips,
                model="Mock Gemini",
                video_url=video_url,
                source_type=source_type,
                source_url=canonical_url,
                output_language=request.output_language,
            )
            yield _sse({
                "step": 4,
                "step_progress": 100,
                "overall_progress": 100,
                "stage": "Analysis Complete",
                "detail": "Generated 3 viral clip candidates successfully.",
                "done": True,
                "result": result.model_dump()
            })
            return

        is_long_video = duration > 3600
        is_auto_clip_count = False
        target_count_num = None
        if request.target_clip_count is not None:
            if isinstance(request.target_clip_count, str) and request.target_clip_count.lower() == 'auto':
                is_auto_clip_count = True
            else:
                try:
                    target_count_num = int(request.target_clip_count)
                    if target_count_num <= 0:
                        is_auto_clip_count = True
                except (ValueError, TypeError):
                    is_auto_clip_count = True
        else:
            is_auto_clip_count = True

        if not is_auto_clip_count and target_count_num:
            N = target_count_num
            if N <= 5:
                min_clips = max(1, N - 1)
                max_clips = N + 2
            elif N <= 10:
                min_clips = max(1, N - 2)
                max_clips = N + 3
            else:
                min_clips = max(1, N - 5)
                max_clips = N + 5
            clip_range = f"{min_clips}-{max_clips}"
            clip_count_instruction = (
                f"TARGET CLIP COUNT: Approximately {clip_range} clips. "
                f"Identify the highest-quality, most viral segments within this range."
            )
        else:
            if duration <= 300:
                auto_clip_target = "3-5"
            elif duration <= 900:
                auto_clip_target = "5-10"
            elif duration <= 1800:
                auto_clip_target = "8-15"
            elif duration <= 3600:
                auto_clip_target = "10-20"
            else:
                auto_clip_target = "15-25"

            clip_range = f"{auto_clip_target} clips (AI-selected based on viral potential)"
            clip_count_instruction = (
                f"DYNAMIC AUTO CLIP COUNT & TOPIC CURATION RULES:\n"
                f"- Extract approximately {auto_clip_target} high-impact, standalone viral clips based on the most captivating moments in this video.\n"
                f"- High-Interest Standalone Topics Required: Every single clip MUST focus on an interesting, distinct, and compelling topic, idea, debate, story, funny moment, or revelation. Do NOT produce repetitive, weak, or trivial filler clips."
            )

        # ── Step 4: Detect language, translate if needed, and build prompt ──────
        detected_lang = detect_transcript_language(enriched_transcript, title)
        lang_code = detected_lang.get('code', 'en')
        lang_name = detected_lang.get('name', 'English')
        output_lang_code, output_lang_name = _resolve_output_language(
            request.output_language, lang_code, lang_name
        )
        translation_needed = output_lang_code != lang_code
        logger.info(
            f"Detected video language: {lang_name} ({lang_code}) - confidence {detected_lang.get('confidence', 0.0)} | "
            f"Output language: {output_lang_name} ({output_lang_code})"
        )

        requested_model = (request.model or '').strip()
        if any(dep in requested_model.lower() for dep in ['gemini-1.0', 'gemini-pro-vision']):
            logger.info(f"Requested model '{requested_model}' is outdated. Selecting the newest available Flash model.")
            requested_model = ''

        # Create the client early because it is also used for transcript translation.
        client = genai.Client(api_key=gemini_key, http_options=types.HttpOptions(timeout=120000))

        # Discover all available Flash models for the user's API key
        discovered_flash = await asyncio.to_thread(get_flash_models_for_key, client)

        # The UI can still hold an old saved model name (for example
        # gemini-2.5-flash) that now returns 404 for new API keys. Prefer the
        # newest model that this key can actually use instead of wasting a call.
        if discovered_flash and (not requested_model or (
            'flash' in requested_model.lower() and requested_model not in discovered_flash
        )):
            if requested_model:
                logger.info(
                    f"Requested model '{requested_model}' is not available for this key; "
                    f"using {discovered_flash[0]} instead."
                )
            requested_model = discovered_flash[0]
        elif not requested_model:
            requested_model = KNOWN_FLASH_MODELS[0]

        # Build models_to_try (capped at top 4 to prevent prolonged delays):
        models_to_try = [requested_model]
        for fm in discovered_flash:
            if fm not in models_to_try:
                models_to_try.append(fm)
        if not discovered_flash:
            for km in KNOWN_FLASH_MODELS:
                if km not in models_to_try:
                    models_to_try.append(km)

        models_to_try = models_to_try[:4]
        logger.info(f"Flash fallback chain prepared: {models_to_try}")

        # 1.0.7: subtitle translation is high-volume but low-complexity. Prefer
        # Flash Lite models that THIS API key actually reported via ListModels.
        # Never inject hardcoded legacy names here: models such as
        # gemini-1.5-flash-8b have been retired and return 404 for new keys.
        translation_models = [
            m for m in models_to_try
            if 'lite' in m.lower() or '8b' in m.lower()
        ]
        for model in discovered_flash:
            if (
                ('lite' in model.lower() or '8b' in model.lower())
                and model not in translation_models
            ):
                translation_models.append(model)
        for model in models_to_try:
            if model not in translation_models:
                translation_models.append(model)
        # Extra safety: drop retired model IDs even if discovery returned them.
        translation_models = [
            m for m in translation_models
            if m not in {"gemini-1.5-flash-8b", "gemini-1.0", "gemini-pro-vision"}
        ][:3]
        logger.info(f"Flash translation chain prepared: {translation_models}")

        output_transcript = enriched_transcript
        if translation_needed:
            total_lines = len(output_transcript)
            total_chunks = max(
                1,
                (total_lines + TRANSLATION_CHUNK_SIZE - 1) // TRANSLATION_CHUNK_SIZE,
            )
            translated_output = []
            logger.info(
                f"Translating {total_lines} transcript lines from {lang_name} to "
                f"{output_lang_name} in {total_chunks} chunk(s)."
            )

            for chunk_index in range(total_chunks):
                start_idx = chunk_index * TRANSLATION_CHUNK_SIZE
                end_idx = min(total_lines, start_idx + TRANSLATION_CHUNK_SIZE)
                chunk = output_transcript[start_idx:end_idx]
                progress_pct = int(((chunk_index + 1) / total_chunks) * 100)

                yield _sse({
                    "step": 3,
                    "step_progress": 100,
                    "overall_progress": min(71, 66 + int(progress_pct * 0.05)),
                    "stage": f"Translating Transcript to {output_lang_name}",
                    "detail": f"Translating subtitle lines {start_idx + 1}-{end_idx} of {total_lines} to {output_lang_name}...",
                    "message": f"Translating transcript to {output_lang_name} ({progress_pct}%)..."
                })

                try:
                    translated_texts = await asyncio.wait_for(
                        asyncio.to_thread(
                            _translate_transcript_chunk,
                            client,
                            translation_models,
                            chunk,
                            lang_name,
                            output_lang_name,
                        ),
                        timeout=TRANSLATION_TIMEOUT_SEC,
                    )
                except Exception as e:
                    logger.error(f"Transcript translation failed: {e}")
                    yield _sse({
                        "error": (
                            f"Gagal menerjemahkan transkrip ke {output_lang_name}: {e}"
                        ),
                        "status": 500,
                    })
                    return

                for line, translated_text in zip(chunk, translated_texts):
                    translated_line = dict(line)
                    translated_line["text"] = translated_text
                    translated_output.append(translated_line)

            output_transcript = translated_output
            yield _sse({
                "step": 3,
                "step_progress": 100,
                "overall_progress": 71,
                "stage": f"{output_lang_name} Transcript Ready",
                "detail": f"Translated {total_lines} subtitle lines to {output_lang_name}.",
                "message": f"Transcript translated to {output_lang_name}."
            })

        transcript_dump = []
        for line in output_transcript:
            eng = f"|{line['engagement']:.2f}" if heatmap and line['engagement'] > 0 else ""
            transcript_dump.append(f"{line['start']:.1f}|{line['end']:.1f}{eng} {line['text']}")

        MAX_LINES = 3500 if is_long_video else 2000
        if len(transcript_dump) > MAX_LINES:
            logger.warning(f"Transcript {len(transcript_dump)} lines — truncating to {MAX_LINES}.")
            transcript_dump = transcript_dump[:MAX_LINES]

        transcript_text = "\n".join(transcript_dump)

        is_auto_duration = str(request.duration).lower() == "auto"
        if is_auto_duration:
            dur_range = "Auto dynamic length (~15s to ~90s max)"
            duration_instruction = (
                "DYNAMIC AUTO CLIP DURATION GUIDELINES:\n"
                "- Intelligently adjust the duration of each individual clip based on its natural narrative flow and context so that NO CONTEXT, setup, premise, punchline, or explanation is cut off mid-thought.\n"
                "- Generate variant clip durations naturally: ranging flexibly from approximately 15 seconds up to around 90 seconds (1 minute 30 seconds maximum). Do NOT force all clips to be the same length (some can be ~20-30s, some ~40-60s, and deeper discussions or complex stories can be up to around 90s).\n"
                "- Strict maximum constraint: No clip should ever exceed 90 seconds (1 minute 30 seconds). Always ensure clips begin and end cleanly at complete sentence boundaries without mid-word or mid-sentence cuts."
            )
        else:
            dur_target = {"15s": "10-20s", "30s": "20-40s", "60s": "45-75s"}.get(request.duration, "20-40s")
            dur_range = dur_target
            duration_instruction = f"Target clip length: {dur_target}. Keep clips tightly focused around this duration."

        heatmap_note = (
            "Columns: start|end|audience_interest(0-1). Prioritise high-interest peaks."
            if heatmap else
            "No audience interest data. Use content hooks, energy, and story arcs."
        )
        focus_instruction = ""
        if request.custom_prompt and request.custom_prompt.strip():
            focus_instruction = (
                f"CRITICAL USER SEARCH FOCUS:\n"
                f"The user specifically wants you to find clips matching the following query/theme: \"{request.custom_prompt.strip()}\".\n"
                f"Prioritize and tailor your selection of viral clips to fit this request, while still ensuring they make good standalone clips.\n"
                f"IMPORTANT: Regardless of the language this query was typed in, your generated titles, summaries, quotes, and captions MUST BE IN {output_lang_name.upper()}. DO NOT switch to the language of the search query.\n\n"
            )

        channel_context = f"- Channel / Host / Creator: {channel}\n" if channel else ""

        prompt = (
            f"You are an expert viral video clip editor finding top clip candidates for TikTok, Instagram Reels, and YouTube Shorts.\n"
            f"Analyze this YouTube video transcript and find {clip_range} high-performing, standalone clip candidates.\n\n"
            f"VIDEO CONTEXT:\n"
            f"- Video Title: {title}\n"
            f"{channel_context}"
            f"- Video Duration: {int(start_bound)}s to {int(end_bound)}s (Total: {int(duration)}s) | Target clip length: {dur_range}\n"
            f"- Heatmap: {heatmap_note}\n"
            f"- DETECTED SOURCE SPOKEN LANGUAGE: {lang_name} (Code: '{lang_code}')\n"
            f"- REQUIRED OUTPUT LANGUAGE: {output_lang_name} (Code: '{output_lang_code}')\n\n"
            f"================================================================================\n"
            f"CRITICAL MANDATORY OUTPUT LANGUAGE RULE:\n"
            f"================================================================================\n"
            f"THE REQUIRED OUTPUT LANGUAGE IS: {output_lang_name.upper()} (Language Code: '{output_lang_code}').\n"
            f"YOU MUST GENERATE 100% OF ALL CONTENT STRICTLY AND EXCLUSIVELY IN {output_lang_name.upper()}.\n\n"
            f"1. NEVER OUTPUT IN A DIFFERENT LANGUAGE!\n"
            f"   - The transcript below is already written in {output_lang_name}.\n"
            f"   - If the source video was in another language, it has already been translated for you. Do NOT switch back to the source language.\n"
            f"   - Even if the user's prompt or search query was written in another language, your output MUST REMAIN 100% IN {output_lang_name.upper()}.\n"
            f"   - Do NOT translate into a third language.\n"
            f"   - If the output language is Indonesian and speakers use Arabic loanwords or Islamic greetings, keep them as part of Indonesian; do NOT switch the whole output to Arabic.\n"
            f"2. Strict field requirements in {output_lang_name.upper()}:\n"
            f"   - `summary`: In {output_lang_name.upper()}.\n"
            f"   - `title`: Catchy title in {output_lang_name.upper()}, max 8 words.\n"
            f"   - `title_suggestion`: Alternative title in {output_lang_name.upper()}.\n"
            f"   - `caption_suggestion`: Engaging social caption in {output_lang_name.upper()}.\n"
            f"   - `hashtag_suggestion`: Relevant hashtags in {output_lang_name.upper()}.\n"
            f"   - `key_quotes`: MUST be direct quotes from the transcript below, in {output_lang_name.upper()}.\n"
            f"================================================================================\n\n"
            f"{duration_instruction}\n\n"
            f"{clip_count_instruction}\n\n"
            f"{focus_instruction}"
            f"CRITICAL TITLE & ATTRIBUTION RULES (NO FIRST-PERSON 'I' OR 'ME'):\n"
            f"1. NEVER write clip titles or title suggestions using first-person pronouns ('I', 'me', 'my', 'mine', 'myself', or equivalents in other languages such as 'saya', 'aku', 'gue')!\n"
            f"2. The user posting or curating these clips is a third-party editor, NOT the person speaking in the video. Titles must NEVER make it look like the clip is expressing the user's personal opinion, story, or reaction (e.g. NEVER write 'Why I think this is bad', 'How I made $100K', 'My biggest mistake', or 'I was shocked' / in Indonesian: NEVER 'Kenapa saya...', 'Cara aku...', 'Opini gue...').\n"
            f"3. ALWAYS attribute statements to the context of the video and the actual person speaking:\n"
            f"   - Use the actual name of the speaker, host, or guest from the video title, channel name ({channel or 'Host'}), or transcript dialogue (e.g. '{channel or 'Speaker'} Explains...', 'Why {channel or 'Host'} Shocked Fans', '[Name] Reveals The Truth' / in Indonesian: '{channel or 'Host'} Menjelaskan...', 'Alasan {channel or 'Host'} Mengungkapkan...').\n"
            f"   - If the speaker's name is not explicitly stated, use their role or descriptive title (e.g. 'Host Reacts...', 'CEO Reveals...', 'Expert Explains...', 'Guest Breaks Down...' / in Indonesian: 'Host Menjelaskan...', 'Pakar Membongkar...').\n"
            f"   - Or use objective, curiosity-driven framing (e.g. 'The Real Truth About...', 'How To Master...', 'Why Most People Fail At...', 'The Harsh Reality of...' / in Indonesian: 'Fakta Sebenarnya Tentang...', 'Cara Menguasai...').\n"
            f"4. Keep titles snappy, viral, engaging, and under 8 words.\n\n"
            f"Transcript (start|end[|interest] text, already in {output_lang_name}):\n---\n{transcript_text}\n---\n\n"
            f"Rules: use exact seconds from transcript; clips must start/end at sentence boundaries; do not overlap.\n"
            f"Return clips sorted by virality_score desc."
        )

        yield _sse({
            "step": 4,
            "step_progress": 10,
            "overall_progress": 72,
            "stage": "Language & Context Assembly",
            "detail": f"Source language: {lang_name} ({lang_code}) → Output: {output_lang_name} ({output_lang_code}). Aligning {len(transcript_dump)} dialogue segments for {requested_model}...",
            "model": requested_model,
            "message": f"Output language: {output_lang_name}. Preparing {requested_model}..."
        })

        response = None
        last_error = None
        encountered_quota_error = None
        analysis_data = None
        successful_model = None

        for idx, model_name in enumerate(models_to_try):
            next_model_hint = models_to_try[idx + 1] if idx + 1 < len(models_to_try) else None
            # One quick retry for transient 500/503 responses. Timeouts and
            # quota/404 errors still fall through immediately to the next model.
            MAX_RETRIES = 2
            MODEL_TIMEOUT_SEC = 120.0  # 120s best-practice timeout for comprehensive video analysis
            
            for attempt in range(MAX_RETRIES):
                if attempt > 0:
                    wait = 2
                    yield _sse({
                        "step": 4,
                        "step_progress": 25,
                        "overall_progress": 75,
                        "stage": "Transient Retry",
                        "detail": f"{model_name} busy — waiting {wait}s before retry ({attempt + 1}/{MAX_RETRIES})...",
                        "model": model_name,
                        "message": f"{model_name} is busy — waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}..."
                    })
                    await asyncio.sleep(wait)
                
                yield _sse({
                    "step": 4,
                    "step_progress": 18,
                    "overall_progress": 74,
                    "stage": "Neural Model Dispatch",
                    "detail": f"Dispatched {len(transcript_dump)} lines to {model_name}...",
                    "model": model_name,
                    "message": f"Calling {model_name} (attempt {attempt + 1}/{MAX_RETRIES})..."
                })
                
                # Execute Gemini call with heartbeat and balanced timeout
                task = asyncio.create_task(asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=VideoAnalysis,
                        temperature=0.2,
                        max_output_tokens=65536,
                    )
                ))
                
                call_start = asyncio.get_event_loop().time()
                timed_out = False
                while not task.done():
                    done, _ = await asyncio.wait([task], timeout=1.5)
                    if not done:
                        elapsed = int(asyncio.get_event_loop().time() - call_start)
                        if elapsed >= MODEL_TIMEOUT_SEC:
                            logger.warning(f"Model {model_name} exceeded {MODEL_TIMEOUT_SEC}s timeout. Cancelling task to fallback...")
                            task.cancel()
                            timed_out = True
                            last_error = TimeoutError(f"{model_name} inference timed out after {MODEL_TIMEOUT_SEC}s")
                            break
                        
                        if elapsed < 8:
                            stage = "Neural Context Loading"
                            detail = f"Transmitting {len(transcript_dump)} timestamped dialogue segments to {model_name}..."
                            step_prog = min(35, 12 + int(elapsed * 2.8))
                        elif elapsed < 20:
                            stage = "Retention Spike Cross-Analysis"
                            detail = f"Correlating viewer retention peaks against speaker dialogue to isolate viral moments..."
                            step_prog = min(55, 35 + int((elapsed - 8) * 1.6))
                        elif elapsed < 40:
                            stage = "Viral Hook & Curiosity Detection"
                            detail = f"Scanning transcript dialogue for opening hooks, punchlines, controversial takes & emotional peaks..."
                            step_prog = min(75, 55 + int((elapsed - 20) * 1.0))
                        elif elapsed < 65:
                            stage = "Coherence & Sentence Boundary Snapping"
                            detail = f"Ensuring clip candidates start and end naturally on sentence boundaries without mid-word cuts..."
                            step_prog = min(88, 75 + int((elapsed - 40) * 0.5))
                        elif elapsed < 90:
                            stage = "Virality Scoring & Selection"
                            display_clip_count = "all high-value" if is_auto_clip_count else f"the top {clip_range}"
                            detail = f"Calculating virality coefficients (1-100) and selecting {display_clip_count} highest potential clips..."
                            step_prog = min(94, 88 + int((elapsed - 65) * 0.24))
                        else:
                            stage = "Social Media Metadata Synthesis"
                            detail = f"Drafting attention-grabbing titles, social captions, and targeted hashtags ({elapsed}s)..."
                            step_prog = min(96, 94 + min(2, int((elapsed - 90) * 0.07)))

                        overall_prog = 70 + int(step_prog * 0.28)
                        yield _sse({
                            "step": 4,
                            "keepalive": True,
                            "step_progress": step_prog,
                            "overall_progress": overall_prog,
                            "stage": stage,
                            "detail": detail,
                            "model": model_name,
                            "elapsed": elapsed,
                            "message": f"[{model_name} | {elapsed}s] {stage}: {detail}"
                        })
                
                if timed_out:
                    break
                
                try:
                    resp_candidate = await task
                    last_error = None
                    
                    # Parse structured response
                    parsed_data = None
                    if hasattr(resp_candidate, 'parsed') and resp_candidate.parsed is not None:
                        parsed = resp_candidate.parsed
                        raw_clips = getattr(parsed, 'clips', []) or []
                        if raw_clips:
                            parsed_data = {
                                "summary": getattr(parsed, 'summary', ''),
                                "clips": [
                                    {
                                        "title": sanitize_first_person_title(getattr(c, 'title', ''), channel, lang=output_lang_code),
                                        "start_time": getattr(c, 'start_time', 0.0),
                                        "end_time": getattr(c, 'end_time', 0.0),
                                        "hook_time": getattr(c, 'hook_time', None),
                                        "virality_score": getattr(c, 'virality_score', 0),
                                        "key_quotes": getattr(c, 'key_quotes', []),
                                        "title_suggestion": sanitize_first_person_title(getattr(c, 'title_suggestion', ''), channel, lang=output_lang_code),
                                        "caption_suggestion": getattr(c, 'caption_suggestion', ''),
                                        "hashtag_suggestion": getattr(c, 'hashtag_suggestion', ''),
                                    }
                                    for c in raw_clips
                                ]
                            }
                    
                    # Lenient fallback parser (repairs truncated/unescaped JSON from text)
                    if parsed_data is None and hasattr(resp_candidate, 'text') and resp_candidate.text:
                        parsed_data = parse_lenient_json_analysis(resp_candidate.text, channel, output_lang_code)

                    if parsed_data is not None:
                        clips_found = len(parsed_data.get('clips', []))
                        if clips_found == 0 and next_model_hint is not None:
                            logger.warning(f"{model_name} returned 0 clips. Will try next flash model {next_model_hint}...")
                            yield _sse({
                                "step": 4,
                                "step_progress": 40,
                                "overall_progress": 78,
                                "stage": "Flash Model Fallback",
                                "detail": f"{model_name} returned 0 clips — switching to {next_model_hint} for deeper extraction...",
                                "model": next_model_hint,
                                "message": f"{model_name} returned 0 clips — switching to {next_model_hint}..."
                            })
                            last_error = Exception(f"{model_name} returned 0 clips")
                            break
                        
                        response = resp_candidate
                        analysis_data = parsed_data
                        successful_model = model_name
                        break
                    else:
                        last_error = Exception(f"{model_name} returned empty or unparseable response")
                        break
                        
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    logger.warning(f"Error from {model_name} (attempt {attempt + 1}): {e}")
                    
                    if any(x in err_str for x in ('429', 'quota', 'resource exhausted', 'rate limit')):
                        encountered_quota_error = e
                        break

                    if any(x in err_str for x in ('404', 'not found', 'not supported')):
                        break
                    
                    is_server_busy = any(x in err_str for x in ('503', 'unavailable', 'overloaded', '500', 'internal'))
                    if not is_server_busy:
                        break
            
            if analysis_data is not None and response is not None:
                break
                
            if next_model_hint is not None:
                err_summary = "quota reached" if any(x in str(last_error).lower() for x in ('429', 'quota', 'rate limit')) else \
                              "not available or deprecated" if "404" in str(last_error) else \
                              "temporarily busy"
                yield _sse({
                    "step": 4,
                    "step_progress": 35,
                    "overall_progress": 76,
                    "stage": "Flash Fallback",
                    "detail": f"{model_name} {err_summary} — switching to fallback {next_model_hint}...",
                    "model": next_model_hint,
                    "message": f"{model_name} {err_summary} — switching to flash fallback model {next_model_hint}..."
                })

        if analysis_data is None:
            # If any model in the fallback chain suffered quota exhaustion, prioritize showing the quota explanation
            error_to_report = encountered_quota_error or last_error
            if error_to_report is not None:
                err_str = str(error_to_report).lower()
                if any(x in err_str for x in ('429', 'quota', 'resource exhausted', 'rate limit')):
                    yield _sse({
                        "error": "Quota limit reached across all available Gemini Flash models for this API key. Free keys have a request limit per minute. Please change your API key, generate a fresh free key at aistudio.google.com, or wait 30–60 seconds before trying again.",
                        "status": 429
                    })
                elif any(x in err_str for x in ('503', 'unavailable', 'overloaded')):
                    yield _sse({
                        "error": "Google Gemini servers are currently experiencing high demand across all Flash models. Please change to a different Gemini API key or wait a few moments and try again.",
                        "status": 503
                    })
                elif any(x in err_str for x in ('401', '403', 'api_key', 'invalid', 'permission')):
                    yield _sse({
                        "error": "Invalid or restricted Gemini API key. Please change your API key or generate a new free key at aistudio.google.com.",
                        "status": 401
                    })
                elif any(x in err_str for x in ('404', 'not found', 'not supported')):
                    models_preview = ', '.join(models_to_try[:3])
                    yield _sse({
                        "error": f"All tested Gemini Flash models ({models_preview}...) were unavailable or not supported for this API key. Please change your Gemini API key or generate a new one at aistudio.google.com.",
                        "status": 404
                    })
                else:
                    logger.error(f"Gemini error after all fallback models: {error_to_report}")
                    yield _sse({
                        "error": f"AI analysis failed across all available Flash models ({str(error_to_report)}). Please change your Gemini API key or try again in a few moments.",
                        "status": 500
                    })
            else:
                yield _sse({
                    "error": "No response received after trying all available Gemini Flash models. Please change your Gemini API key or try again in a few moments.",
                    "status": 500
                })
            return

        # Fallback clip synthesis if 0 clips were returned after all models
        if len(analysis_data.get('clips', [])) == 0 and enriched_transcript:
            logger.info("Generating fallback clips from heatmap and transcript segments...")
            sorted_lines = sorted(enriched_transcript, key=lambda l: l.get('engagement', 0.0), reverse=True)
            candidate_starts = []
            for l in sorted_lines:
                s = l['start']
                if not any(abs(s - existing) < 25.0 for existing in candidate_starts):
                    candidate_starts.append(s)
                if len(candidate_starts) >= 5:
                    break
            
            fallback_clips_list = []
            for i, st in enumerate(candidate_starts):
                if request.duration == "15s":
                    target_len = 15.0
                elif request.duration == "60s":
                    target_len = 60.0
                elif request.duration == "auto":
                    auto_lens = [25.0, 45.0, 75.0, 35.0, 60.0, 85.0, 20.0, 50.0]
                    target_len = auto_lens[i % len(auto_lens)]
                else:
                    target_len = 30.0
                et = min(duration, st + min(90.0, target_len))
                seg_lines = [l['text'] for l in output_transcript if max(l['start'], st) < min(l['end'], et)]
                seg_text = " ".join(seg_lines).strip()
                preview = seg_text[:60] + "..." if len(seg_text) > 60 else seg_text or f"Viral Highlight #{i+1}"
                if output_lang_code == 'id':
                    fallback_clips_list.append({
                        "title": f"Momen Menarik #{i+1}",
                        "start_time": st,
                        "end_time": et,
                        "hook_time": st,
                        "virality_score": max(70, int(95 - i * 5)),
                        "key_quotes": [seg_text[:80]] if seg_text else [],
                        "title_suggestion": f"Cuplikan Pilihan #{i+1}",
                        "caption_suggestion": f"Momen terbaik dari video: {preview} #viral #trending",
                        "hashtag_suggestion": "#viral #shorts #trending"
                    })
                elif output_lang_code == 'es':
                    fallback_clips_list.append({
                        "title": f"Momento Destacado #{i+1}",
                        "start_time": st,
                        "end_time": et,
                        "hook_time": st,
                        "virality_score": max(70, int(95 - i * 5)),
                        "key_quotes": [seg_text[:80]] if seg_text else [],
                        "title_suggestion": f"Momento Imperdible #{i+1}",
                        "caption_suggestion": f"Momento clave del video: {preview} #viral #trending",
                        "hashtag_suggestion": "#viral #shorts #trending"
                    })
                else:
                    fallback_clips_list.append({
                        "title": f"Key Highlight #{i+1}",
                        "start_time": st,
                        "end_time": et,
                        "hook_time": st,
                        "virality_score": max(70, int(95 - i * 5)),
                        "key_quotes": [seg_text[:80]] if seg_text else [],
                        "title_suggestion": f"Must Watch Moment #{i+1}",
                        "caption_suggestion": f"Key highlight from video: {preview} #viral #trending",
                        "hashtag_suggestion": "#viral #shorts #trending"
                    })
            analysis_data['clips'] = fallback_clips_list
            if not analysis_data.get('summary'):
                if output_lang_code == 'id':
                    analysis_data['summary'] = f"Analisis video \"{title}\" menemukan {len(fallback_clips_list)} segmen cuplikan pilihan. #viral #highlights"
                elif output_lang_code == 'es':
                    analysis_data['summary'] = f"Análisis de \"{title}\" identificando {len(fallback_clips_list)} segmentos clave. #viral #highlights"
                else:
                    analysis_data['summary'] = f"Analysis of \"{title}\" identifying {len(fallback_clips_list)} key segments. #viral #highlights"

        clip_count = len(analysis_data.get('clips', []))
        yield _sse({
            "step": 4,
            "step_progress": 98,
            "overall_progress": 98,
            "stage": "Clip Verification & Alignment",
            "detail": f"Verified {clip_count} clip segments with precise video timestamps and key quotes in {output_lang_name}.",
            "model": successful_model or requested_model,
            "message": f"Found {clip_count} viral clip candidates ({output_lang_name}) with {successful_model or requested_model} — reconstructing transcripts..."
        })
        logger.info(f"Gemini analysis complete with {successful_model or requested_model}. Found {clip_count} clips in {output_lang_name}.")

        # Reconstruct clip transcripts from the translated output transcript
        final_clips = []
        for raw_clip in analysis_data.get('clips', []):
            start = raw_clip.get('start_time', 0.0)
            end   = raw_clip.get('end_time', 0.0)
            hook  = raw_clip.get('hook_time')
            if hook is None or not (start <= hook <= end):
                hook = start
            
            # Enforce max 90 seconds (1m 30s) duration constraint for auto duration mode
            if is_auto_duration and (end - start) > 90.0:
                max_end = start + 90.0
                best_end = max_end
                for l in enriched_transcript:
                    l_end = l.get('end', 0.0)
                    if start + 15.0 <= l_end <= max_end:
                        best_end = l_end
                end = best_end
            
            clip_lines = [
                line.get("text", "")
                for line in output_transcript
                if max(line.get("start", 0.0), start) < min(line.get("end", 0.0), end)
            ]
            
            # Ensure hashtags are always lowercase
            caption_sug = lowercase_hashtags_in_string(raw_clip.get('caption_suggestion', ''))
            hashtag_sug = lowercase_hashtags_in_string(raw_clip.get('hashtag_suggestion', ''))
            
            final_clips.append(ViralClip(
                title=sanitize_first_person_title(raw_clip.get('title', ''), channel, lang=output_lang_code),
                start_time=start,
                end_time=end,
                hook_time=hook,
                virality_score=raw_clip.get('virality_score', 0),
                key_quotes=raw_clip.get('key_quotes') or [],
                transcript=" ".join(clip_lines),
                title_suggestion=sanitize_first_person_title(raw_clip.get('title_suggestion', ''), channel, lang=output_lang_code),
                caption_suggestion=caption_sug,
                hashtag_suggestion=hashtag_sug
            ))

        # Enforce max constraint of ~200 clips for auto clip count
        if is_auto_clip_count and len(final_clips) > 200:
            final_clips = final_clips[:200]

        response_heatmap = [
            HeatmapPoint(
                start_time=float(pt.get('start_time', 0.0)),
                end_time=float(pt.get('end_time', 0.0)),
                value=float(pt.get('value', 0.0))
            )
            for pt in (heatmap or [])
        ]

        response_transcript = [
            TranscriptLine(
                start=float(line["start"]),
                end=float(line["end"]),
                text=line["text"],
                engagement=line.get("engagement")
            )
            for line in output_transcript
        ]

        # Ensure hashtags are lowercase in the overall summary
        clean_summary = lowercase_hashtags_in_string(analysis_data.get("summary", ""))

        final_result = AnalyzeResponse(
            video_id=video_id,
            title=title,
            channel=channel,
            duration=duration,
            heatmap=response_heatmap,
            summary=clean_summary,
            clips=final_clips,
            transcript=response_transcript,
            model=successful_model or requested_model,
            video_url=video_url,
            source_type=source_type,
            source_url=canonical_url,
            source_language=lang_code,
            output_language=output_lang_code
        )

        yield _sse({"done": True, "result": final_result.model_dump()})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection":    "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
