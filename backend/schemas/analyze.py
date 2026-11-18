from typing import List, Optional, Union
from pydantic import BaseModel, Field

class ViralClip(BaseModel):
    title: str = Field(description="Catchy clip title, max 8 words. MUST NEVER use first-person pronouns ('I', 'me', 'my', 'saya', 'aku'). Attribute to the speaker/host by name, role, or use objective framing.")
    start_time: float = Field(description="Clip start in seconds, aligned to a sentence boundary")
    end_time: float = Field(description="Clip end in seconds, aligned to a sentence boundary")
    hook_time: float = Field(description="Absolute timestamp in seconds from video start where the potential hook occurs inside this clip range (must be >= start_time and <= end_time)")
    virality_score: int = Field(description="Virality score 1-100")
    key_quotes: List[str] = Field(description="1-2 key quotes from the clip")
    transcript: str = Field(description="Spoken text of the clip")
    title_suggestion: str = Field(default="", description="Catchy alternative title suggestion. MUST NEVER use first-person pronouns ('I', 'me', 'my'). Attribute to speaker or objective topic.")
    caption_suggestion: str = Field(default="", description="Engaging social media caption suggestion attributing quotes or insights to the speaker.")
    hashtag_suggestion: str = Field(default="", description="Relevant hashtags suggestion (e.g. #hashtag1 #hashtag2)")

class ViralClipGemini(BaseModel):
    title: str = Field(description="Catchy clip title, max 8 words, in the REQUIRED OUTPUT LANGUAGE requested by the prompt. NEVER use first-person pronouns ('I', 'me', 'my', 'myself', 'aku', 'saya'). Attribute to the person speaking by name, host/guest title, or use third-person objective framing so it does not look like the user's opinion.")
    start_time: float = Field(description="Clip start in seconds, aligned to a sentence boundary")
    end_time: float = Field(description="Clip end in seconds, aligned to a sentence boundary")
    hook_time: float = Field(description="Absolute timestamp in seconds from video start where the potential hook occurs inside this clip range (must be >= start_time and <= end_time)")
    virality_score: int = Field(description="Virality score 1-100")
    key_quotes: List[str] = Field(description="1-2 direct quotes from the provided transcript, written in the REQUIRED OUTPUT LANGUAGE")
    title_suggestion: str = Field(default="", description="Catchy alternative title suggestion in the REQUIRED OUTPUT LANGUAGE. STRICT RULE: NEVER use first-person ('I', 'me', 'my', 'saya', 'aku'). Attribute to the speaker/host/guest by name or topic.")
    caption_suggestion: str = Field(default="", description="Engaging social media caption suggestion written in the REQUIRED OUTPUT LANGUAGE, attributing insights or story to the speaker.")
    hashtag_suggestion: str = Field(default="", description="Relevant hashtags suggestion in the REQUIRED OUTPUT LANGUAGE (e.g. #hashtag1 #hashtag2)")

class VideoAnalysis(BaseModel):
    summary: str = Field(description="1-2 sentence video summary in the REQUIRED OUTPUT LANGUAGE requested by the prompt, followed by 2-4 relevant hashtags")
    clips: List[ViralClipGemini] = Field(description="List of viral clip candidates, sorted by virality_score desc")

class TranslatedLine(BaseModel):
    index: int = Field(description="Zero-based index of the subtitle line in the input array")
    text: str = Field(description="Translated subtitle text")

class TranslatedTranscript(BaseModel):
    lines: List[TranslatedLine] = Field(description="Translated subtitle lines, preserving the original line count and indices")

class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="YouTube, Google Drive, Facebook, Threads, Instagram, TikTok, X, or local upload reference")
    duration: str = Field("30s", description="Target clip duration: '15s', '30s', '60s', or 'auto'")
    api_key: Optional[str] = Field(None, description="Optional custom Gemini API key provided by the user")
    model: Optional[str] = Field("gemini-3.8-flash", description="Preferred Gemini model name")
    custom_prompt: Optional[str] = Field(None, description="Optional custom focus prompt for clips search")
    range_start: Optional[float] = Field(None, description="Search range start in seconds")
    range_end: Optional[float] = Field(None, description="Search range end in seconds")
    subtitles: Optional[str] = Field(None, description="Optional manual subtitles text (SRT or TXT)")
    subtitles_filename: Optional[str] = Field(None, description="Optional manual subtitles filename")
    target_clip_count: Optional[Union[int, str]] = Field(None, description="Optional target number of clips or 'auto'")
    output_language: Optional[str] = Field("source", description="Target language for titles, captions, quotes and subtitles: 'source' to follow the video, or 'id' for Bahasa Indonesia")
    proxy: Optional[str] = Field(None, description="Optional custom proxy URL")
    cookies: Optional[str] = Field(None, description="Optional user YouTube cookies from browser LocalStorage")

class HeatmapPoint(BaseModel):
    start_time: float
    end_time: float
    value: float

class TranscriptLine(BaseModel):
    start: float
    end: float
    text: str
    engagement: Optional[float] = None

class AnalyzeResponse(BaseModel):
    video_id: str
    title: str
    channel: Optional[str] = None
    duration: float
    heatmap: List[HeatmapPoint]
    summary: str
    clips: List[ViralClip]
    transcript: Optional[List[TranscriptLine]] = None
    model: Optional[str] = None
    video_url: Optional[str] = None
    source_type: Optional[str] = "youtube"
    source_url: Optional[str] = None
    source_language: Optional[str] = None
    output_language: Optional[str] = None
