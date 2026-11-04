from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class RenderSettingsModel(BaseModel):
    aspect_ratio: str = "9:16"
    background_style: str = "black"
    enable_face_tracking: bool = True
    streamer_preset: str = "none"
    facecam_position: Optional[str] = "auto"
    title_text: Optional[str] = None
    title_prefix: Optional[str] = ""
    title_suffix: Optional[str] = ""
    file_name_prefix: Optional[str] = ""
    file_name_suffix: Optional[str] = ""
    title_position: str = "auto"
    title_duration: Optional[str] = "entire"
    subtitles_enabled: Optional[bool] = True
    caption_style: str = "viral_pop"
    caption_font: str = "Outfit"
    title_font: Optional[str] = "Outfit"
    font_size: str = "medium"
    title_font_size: Optional[str] = "medium"
    font_size_px: Optional[int] = None
    title_font_size_px: Optional[int] = None
    text_case: str = "uppercase"
    title_text_case: Optional[str] = "uppercase"
    title_y_percent: Optional[float] = None
    subtitle_y_percent: Optional[float] = None
    subtitle_position_mode: Optional[str] = "bottom"
    subtitle_center_y_percent: Optional[float] = 50.0
    # Background Music
    bgm_enabled: Optional[bool] = False
    bgm_file_path: Optional[str] = None
    bgm_volume: Optional[float] = 25.0
    bgm_start_offset: Optional[float] = 0.0
    # Hook SFX
    hook_sfx_enabled: Optional[bool] = False
    hook_sfx_file_path: Optional[str] = None
    hook_sfx_volume: Optional[float] = 100.0
    # Raw Audio / Voice Boost
    original_audio_volume: Optional[float] = 100.0
    # Watermark
    watermark_enabled: Optional[bool] = False
    watermark_type: Optional[str] = "image"
    watermark_file_path: Optional[str] = None
    watermark_text: Optional[str] = None
    watermark_size: Optional[float] = 20.0
    watermark_opacity: Optional[float] = 80.0
    watermark_x: Optional[float] = 90.0
    watermark_y: Optional[float] = 8.0
    # Custom Facecam Overlay (user's own camera/avatar)
    facecam_overlay_enabled: Optional[bool] = False
    facecam_overlay_path: Optional[str] = None
    facecam_overlay_position: Optional[str] = "bottom_right"
    facecam_overlay_size: Optional[float] = 25.0
    facecam_overlay_opacity: Optional[float] = 100.0
    facecam_overlay_shape: Optional[str] = "square"
    facecam_overlay_mirror: Optional[bool] = False
    # Voice Over (own narration audio)
    voiceover_enabled: Optional[bool] = False
    voiceover_path: Optional[str] = None
    voiceover_volume: Optional[float] = 100.0
    voiceover_delay: Optional[float] = 0.0
    voiceover_pitch: Optional[float] = 0.0
    voiceover_loop: Optional[bool] = True
    # Original audio pitch shift (semitones)
    original_audio_pitch: Optional[float] = 0.0
    # Video color grading (UI-friendly ranges)
    color_brightness: Optional[float] = 0.0   # -100 .. 100
    color_contrast: Optional[float] = 0.0     # -100 .. 100
    color_saturation: Optional[float] = 0.0   # -100 .. 100
    color_hue: Optional[float] = 0.0          # -180 .. 180 degrees
    color_temperature: Optional[float] = 0.0  # -100 (cool) .. 100 (warm)
    hardware_accel: Optional[str] = "auto"
    # Multi-Segment Merged Highlight Video
    render_mode: Optional[str] = "separate"  # "separate" | "merged"
    compilation_title: Optional[str] = None

class RenderBatchRequest(BaseModel):
    video_url: str
    video_id: str
    clips: List[Dict[str, Any]]
    settings: RenderSettingsModel
    transcript: Optional[List[Dict[str, Any]]] = None
    cookies: Optional[str] = None

class RetryBatchRequest(BaseModel):
    clip_indices: Optional[List[int]] = None
    cookies: Optional[str] = None
