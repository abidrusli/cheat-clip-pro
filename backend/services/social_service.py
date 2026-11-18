"""Download public videos from Facebook, Threads, Instagram, TikTok and X.

Facebook/Instagram/TikTok/X are handled by yt-dlp. Threads does not have a
yt-dlp extractor yet, so this module contains a small public-page extractor
that reads the video URLs embedded in the Threads HTML/JSON payload.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
import yt_dlp

from backend.config import UPLOADS_DIR, is_valid_mp4, logger
from backend.video_engine import YT_DLP_CONCURRENT_FRAGMENTS

ProgressCallback = Callable[[str, str, int], None]

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_CRAWLER_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

_PLATFORM_LABELS = {
    "facebook": "Facebook",
    "threads": "Threads",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "twitter": "X / Twitter",
}

_SOCIAL_HOSTS = {
    "facebook": ("facebook.com", "fb.watch", "fb.me"),
    "threads": ("threads.com", "threads.net"),
    "instagram": ("instagram.com", "instagr.am"),
    "tiktok": ("tiktok.com",),
    "twitter": ("twitter.com", "x.com"),
}

_MEDIA_HOST_SUFFIXES = ("fbcdn.net", "cdninstagram.com", "threads.com", "threads.net")

_VIDEO_URL_KEYS = {
    "video_url",
    "playable_url",
    "playable_url_quality_hd",
    "browser_native_hd_url",
    "browser_native_sd_url",
    "hd_src",
    "sd_src",
    "contentUrl",
    "content_url",
}
_VIDEO_LIST_KEYS = {"video_versions", "video_urls", "videos"}


@dataclass
class SocialDownloadResult:
    path: Path
    title: str
    uploader: str
    platform: str
    source_id: str


def _with_scheme(url: str) -> str:
    value = (url or "").strip()
    if value and not re.match(r"^https?://", value, re.I):
        value = "https://" + value.lstrip("/")
    return value


def detect_social_platform(url: str) -> Optional[str]:
    """Returns a supported platform id for a social video URL."""
    value = _with_scheme(url)
    if not value:
        return None
    try:
        host = (urlsplit(value).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None
    for platform, suffixes in _SOCIAL_HOSTS.items():
        if any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
            return platform
    return None


def is_social_video_url(url: str) -> bool:
    return detect_social_platform(url) is not None


def get_social_platform_label(platform: str) -> str:
    return _PLATFORM_LABELS.get(platform, platform.title())


def _source_id(url: str, platform: str) -> str:
    parsed = urlsplit(_with_scheme(url))
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    patterns = {
        "facebook": (
            r"/videos/([A-Za-z0-9_-]+)",
            r"/reel/([A-Za-z0-9_-]+)",
            r"[?&]v=([A-Za-z0-9_-]+)",
        ),
        "threads": (
            r"/(?:@[^/]+/post|t|share)/([A-Za-z0-9_-]+)",
        ),
        "instagram": (
            r"/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)",
        ),
        "tiktok": (
            r"/video/(\d+)",
        ),
        "twitter": (
            r"/status/(\d+)",
        ),
    }
    for pattern in patterns.get(platform, ()):
        match = re.search(pattern, path)
        if match:
            return re.sub(r"[^A-Za-z0-9_-]", "_", match.group(1))[:80]
    return hashlib.sha1(_with_scheme(url).encode("utf-8")).hexdigest()[:16]


def _find_cached(platform: str, source_id: str) -> Optional[Path]:
    if not UPLOADS_DIR.exists():
        return None
    for candidate in UPLOADS_DIR.glob(f"social_{platform}_{source_id}*"):
        if not candidate.is_file() or candidate.stat().st_size < 8 * 1024:
            continue
        if candidate.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
            continue
        if is_valid_mp4(candidate):
            return candidate
    return None


def download_social_video(
    url: str,
    on_progress: Optional[ProgressCallback] = None,
) -> SocialDownloadResult:
    """Downloads a public social video into UPLOADS_DIR and returns its path."""
    value = _with_scheme(url)
    platform = detect_social_platform(value)
    if not platform:
        raise ValueError(
            "Unsupported social link. Use a public Facebook, Threads, Instagram, TikTok or X video link."
        )

    source_id = _source_id(value, platform)
    label = get_social_platform_label(platform)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    cached = _find_cached(platform, source_id)
    if cached:
        if on_progress:
            on_progress("Video Found in Cache", f"Using cached {label} video: {cached.name}", 100)
        return SocialDownloadResult(cached, cached.stem, label, platform, source_id)

    if platform == "threads":
        return _download_threads(value, source_id, on_progress)

    return _download_with_ytdlp(value, platform, source_id, on_progress)


def _progress(on_progress: Optional[ProgressCallback], stage: str, detail: str, pct: int) -> None:
    if on_progress:
        on_progress(stage, detail, max(0, min(100, int(pct))))


def _download_with_ytdlp(
    url: str,
    platform: str,
    source_id: str,
    on_progress: Optional[ProgressCallback],
) -> SocialDownloadResult:
    label = get_social_platform_label(platform)
    output_template = str(UPLOADS_DIR / f"social_{platform}_{source_id}.%(ext)s")
    _progress(on_progress, f"Connecting to {label}", f"Resolving public {label} video...", 8)

    def hook(data: Dict[str, Any]) -> None:
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            if total:
                pct = int(10 + min(82, (downloaded / total) * 82))
                detail = (
                    f"Downloading {label} video: "
                    f"{downloaded / (1024 * 1024):.1f} MB / {total / (1024 * 1024):.1f} MB ({pct}%)"
                )
            else:
                pct = 45
                detail = f"Downloading {label} video: {downloaded / (1024 * 1024):.1f} MB..."
            _progress(on_progress, "Downloading Video", detail, pct)
        elif data.get("status") == "finished":
            _progress(on_progress, "Processing Video", "Merging audio and video streams...", 94)

    common_opts: Dict[str, Any] = {
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "socket_timeout": 35,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": YT_DLP_CONCURRENT_FRAGMENTS,
        "progress_hooks": [hook],
        "http_headers": {"User-Agent": _BROWSER_UA},
    }

    info: Dict[str, Any] = {}
    last_error: Optional[Exception] = None
    for fmt in (
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best[ext=mp4]/best",
        "best[ext=mp4]/best",
    ):
        try:
            opts = dict(common_opts)
            opts["format"] = fmt
            with yt_dlp.YoutubeDL(opts) as ydl:
                extracted = ydl.extract_info(url, download=True)
                if isinstance(extracted, dict):
                    if extracted.get("entries"):
                        entries = list(extracted.get("entries") or [])
                        if entries and isinstance(entries[0], dict):
                            info = entries[0]
                    else:
                        info = extracted
            break
        except Exception as exc:  # yt-dlp raises many different exception types
            last_error = exc
            logger.warning("yt-dlp %s download attempt failed for %s: %s", platform, url, exc)

    candidates: List[Path] = []
    for candidate in UPLOADS_DIR.glob(f"social_{platform}_{source_id}*"):
        if (
            candidate.is_file()
            and candidate.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
            and candidate.stat().st_size > 8 * 1024
            and is_valid_mp4(candidate)
        ):
            candidates.append(candidate)

    if not candidates:
        detail = f" Details: {last_error}" if last_error else ""
        raise RuntimeError(
            f"Could not download this {label} video. Make sure the post is public and contains a video.{detail}"
        )

    chosen = max(candidates, key=lambda p: p.stat().st_size)
    title = str(info.get("title") or info.get("description") or chosen.stem).strip()
    uploader = str(info.get("uploader") or info.get("channel") or info.get("creator") or label).strip()
    _progress(on_progress, "Download Complete", f"{label} video ready: {chosen.name}", 100)
    logger.info("Downloaded %s video %s -> %s", label, url, chosen)
    return SocialDownloadResult(chosen, title[:180], uploader[:120], platform, source_id)


class _ThreadsPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: Dict[str, str] = {}
        self.json_scripts: List[str] = []
        self._script_parts: List[str] = []
        self._capture_script = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").strip().lower()
            if key:
                self.meta[key] = values.get("content", "")
        elif tag == "script":
            script_type = (values.get("type") or "").lower()
            self._capture_script = script_type in ("application/json", "application/ld+json")
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_script:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture_script:
            script = "".join(self._script_parts).strip()
            if script:
                self.json_scripts.append(script)
            self._capture_script = False
            self._script_parts = []


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _iter_json_media(value: Any) -> Iterable[Tuple[str, int, int]]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _VIDEO_URL_KEYS and isinstance(item, str):
                yield item, _as_int(value.get("width")), _as_int(value.get("height"))
            elif key in _VIDEO_LIST_KEYS and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, dict):
                        media_url = entry.get("url") or entry.get("src")
                        if isinstance(media_url, str):
                            yield media_url, _as_int(entry.get("width")), _as_int(entry.get("height"))
                    elif isinstance(entry, str):
                        yield entry, 0, 0
            yield from _iter_json_media(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_media(item)


def _normalise_media_url(value: str, base_url: str) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    candidate = html.unescape(value).replace("\\/", "/").replace("\\u0026", "&").strip()
    candidate = urljoin(base_url, candidate)
    try:
        parsed = urlsplit(candidate)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if not any(host == suffix or host.endswith("." + suffix) for suffix in _MEDIA_HOST_SUFFIXES):
        return None
    return candidate


def _extract_threads_candidates(
    page_html: str,
    meta: Dict[str, str],
    page_url: str,
) -> List[str]:
    scored: List[Tuple[int, str]] = []

    for key in ("og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream"):
        normalised = _normalise_media_url(meta.get(key, ""), page_url)
        if normalised:
            scored.append((10_000_000, normalised))

    parser = _ThreadsPageParser()
    try:
        parser.feed(page_html)
    except Exception:
        pass

    for script in parser.json_scripts:
        try:
            payload = json.loads(script)
        except Exception:
            continue
        for media_url, width, height in _iter_json_media(payload):
            normalised = _normalise_media_url(media_url, page_url)
            if normalised:
                scored.append((width * height, normalised))

    # Some Threads payloads are embedded inside JavaScript rather than a pure
    # JSON script tag. This regex fallback catches the common fields.
    for match in re.finditer(
        r'"(?:video_url|playable_url|playable_url_quality_hd|browser_native_hd_url|'
        r'browser_native_sd_url|hd_src|sd_src|contentUrl)"\s*:\s*"((?:\\.|[^"\\])*)"',
        page_html,
    ):
        raw = match.group(1)
        try:
            decoded = json.loads(f'"{raw}"')
        except Exception:
            decoded = raw.replace("\\/", "/").replace("\\u0026", "&")
        normalised = _normalise_media_url(decoded, page_url)
        if normalised:
            scored.append((0, normalised))

    # De-duplicate while keeping the highest-resolution candidate first.
    best: Dict[str, int] = {}
    for score, media_url in scored:
        best[media_url] = max(best.get(media_url, 0), score)
    return [url for url, _ in sorted(best.items(), key=lambda item: item[1], reverse=True)]


def _threads_page_urls(url: str) -> List[str]:
    parsed = urlsplit(_with_scheme(url))
    host = (parsed.hostname or "").lower()
    netloc = parsed.netloc
    if host.endswith("threads.net"):
        netloc = netloc.replace("threads.net", "threads.com")
    elif not host.endswith("threads.com"):
        return [url]
    primary = urlunsplit((parsed.scheme or "https", netloc, parsed.path, parsed.query, ""))
    alternate = urlunsplit(
        (
            parsed.scheme or "https",
            netloc.replace("threads.com", "threads.net"),
            parsed.path,
            parsed.query,
            "",
        )
    )
    return [primary] if primary == alternate else [primary, alternate]


def _threads_title(meta: Dict[str, str], source_id: str) -> str:
    for key in ("og:title", "twitter:title", "og:description", "description"):
        value = html.unescape(meta.get(key, "")).strip()
        if value:
            return value[:180]
    return f"Threads video {source_id}"


def _download_threads(
    url: str,
    source_id: str,
    on_progress: Optional[ProgressCallback],
) -> SocialDownloadResult:
    _progress(on_progress, "Connecting to Threads", "Reading the public Threads post...", 10)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _CRAWLER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        }
    )

    page_response = None
    last_error: Optional[Exception] = None
    for page_url in _threads_page_urls(url):
        try:
            response = session.get(page_url, timeout=35, allow_redirects=True)
            if response.status_code < 400 and response.text:
                page_response = response
                break
            last_error = RuntimeError(f"Threads returned HTTP {response.status_code}")
        except Exception as exc:
            last_error = exc

    if page_response is None:
        detail = f" Details: {last_error}" if last_error else ""
        raise RuntimeError(
            "Could not open this Threads post. Make sure the link is public and still available." + detail
        )

    final_url = page_response.url or url
    parser = _ThreadsPageParser()
    try:
        parser.feed(page_response.text)
    except Exception:
        pass

    candidates = _extract_threads_candidates(page_response.text, parser.meta, final_url)
    if not candidates:
        raise RuntimeError(
            "No public video was found in this Threads post. The post may be text-only, "
            "private, or Threads may be showing a login page."
        )

    _progress(on_progress, "Downloading Video", f"Found {len(candidates)} video stream(s); downloading...", 35)
    download_session = requests.Session()
    download_headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "*/*",
        "Referer": final_url,
    }

    last_download_error: Optional[Exception] = None
    for index, media_url in enumerate(candidates):
        out_path = UPLOADS_DIR / f"social_threads_{source_id}_{int(time.time())}_{index}.mp4"
        try:
            with download_session.get(
                media_url,
                headers=download_headers,
                stream=True,
                timeout=60,
                allow_redirects=True,
            ) as media_response:
                if media_response.status_code >= 400:
                    raise RuntimeError(f"HTTP {media_response.status_code}")
                content_type = (media_response.headers.get("Content-Type") or "").lower()
                if "text/html" in content_type:
                    raise RuntimeError("Threads returned an HTML page instead of a video stream")

                total_bytes = _as_int(media_response.headers.get("Content-Length"))
                downloaded = 0
                with open(out_path, "wb") as handle:
                    for chunk in media_response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if total_bytes:
                            pct = int(38 + min(56, (downloaded / total_bytes) * 56))
                            detail = (
                                f"Downloading Threads video: {downloaded / (1024 * 1024):.1f} MB / "
                                f"{total_bytes / (1024 * 1024):.1f} MB ({pct}%)"
                            )
                        else:
                            pct = 50
                            detail = f"Downloading Threads video: {downloaded / (1024 * 1024):.1f} MB..."
                        _progress(on_progress, "Downloading Video", detail, pct)

            if out_path.exists() and out_path.stat().st_size > 8 * 1024 and is_valid_mp4(out_path):
                title = _threads_title(parser.meta, source_id)
                uploader_match = re.search(r"/@([^/]+)", urlsplit(final_url).path)
                uploader = uploader_match.group(1) if uploader_match else "Threads"
                _progress(on_progress, "Download Complete", f"Threads video ready: {out_path.name}", 100)
                logger.info("Downloaded Threads video %s -> %s", url, out_path)
                return SocialDownloadResult(out_path, title, uploader, "threads", source_id)
            raise RuntimeError("The downloaded Threads file is not a valid video")
        except Exception as exc:
            last_download_error = exc
            if out_path.exists():
                try:
                    out_path.unlink()
                except Exception:
                    pass

    detail = f" Details: {last_download_error}" if last_download_error else ""
    raise RuntimeError(
        "Could not download the video from this Threads post. It may require login or the media URL expired."
        + detail
    )
