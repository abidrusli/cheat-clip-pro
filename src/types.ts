export interface HeatmapPoint {
  start_time: number;
  end_time: number;
  value: number;
}

export interface TranscriptLine {
  start: number;
  end: number;
  text: string;
  engagement?: number;
}

export interface ViralClip {
  title: string;
  start_time: number;
  end_time: number;
  hook_time?: number;
  virality_score: number;
  key_quotes: string[];
  transcript: string;
  title_suggestion?: string;
  caption_suggestion?: string;
  hashtag_suggestion?: string;
}

export interface AnalyzeResponse {
  video_id: string;
  title: string;
  duration: number;
  heatmap: HeatmapPoint[];
  summary: string;
  clips: ViralClip[];
  transcript?: TranscriptLine[];
  model?: string;
  video_url?: string;
  source_type?: 'youtube' | 'upload' | 'gdrive';
  source_language?: string;
  output_language?: string;
}

export type AspectRatioOption = '9:16' | '1:1' | '4:3' | '16:9' | '16:9_landscape';
export type BackgroundStyle = 'black' | 'blurred';
export type CaptionStyle = 
  | 'viral_pop' 
  | 'beast_punch' 
  | 'cyber_violet' 
  | 'fire_red' 
  | 'electric_cyan' 
  | 'golden_aura' 
  | 'clean_minimal' 
  | 'none';
export type CaptionFont = 
  | 'Outfit' 
  | 'Montserrat' 
  | 'Inter' 
  | 'Impact' 
  | 'Bebas Neue' 
  | 'Anton' 
  | 'Poppins' 
  | 'Arial Black'
  | (string & {});
export type TitlePosition = 'auto' | 'safe_zone' | 'middle' | 'none';
export type TitleDurationOption = 'entire' | '5s' | '10s';
export type SubtitlePositionMode = 'bottom' | 'center';
export type StreamerPreset = 'none' | 'split_top_cam' | 'pip_corner';
export type FacecamPosition = 'auto' | 'bottom_right' | 'top_right' | 'bottom_left' | 'top_left' | 'center' | 'left' | 'right';
export type FontSizeOption = 'small' | 'medium' | 'big' | 'custom';
export type TextCaseOption = 'uppercase' | 'capitalize' | 'lowercase';
export type HardwareAccelOption = 'auto' | 'nvenc' | 'amf' | 'qsv' | 'cpu' | 'browser_wasm';
export type ThumbnailFormat = '16:9' | '9:16' | '1:1' | 'auto';
export type ThumbnailStyle = 'viral' | 'cinematic' | 'neon' | 'clean';

export interface FontItem {
  name: string;
  is_custom: boolean;
  filename?: string | null;
  url?: string | null;
}

export interface HardwareAccelInfo {
  status: string;
  active_default: string;
  recommended: string;
  support: {
    nvenc: boolean;
    amf: boolean;
    qsv: boolean;
    cpu: boolean;
    recommended: string;
  };
  options: Array<{
    id: HardwareAccelOption;
    label: string;
    sub: string;
    available: boolean;
  }>;
}

export interface RenderSettings {
  renderEngine?: 'server' | 'client';
  aspectRatio: AspectRatioOption;
  backgroundStyle: BackgroundStyle;
  enableFaceTracking: boolean;
  streamerPreset: StreamerPreset;
  facecamPosition?: FacecamPosition;
  titleText?: string;
  titlePrefix?: string;
  titleSuffix?: string;
  fileNamePrefix?: string;
  fileNameSuffix?: string;
  titlePosition: TitlePosition;
  titleDuration?: TitleDurationOption;
  titleFont?: CaptionFont;
  titleFontSize?: FontSizeOption;
  titleFontSizePx?: number;
  titleTextCase?: TextCaseOption;
  subtitlesEnabled?: boolean;
  captionStyle: CaptionStyle;
  captionFont: CaptionFont;
  fontSize: FontSizeOption;
  fontSizePx?: number;
  textCase: TextCaseOption;
  titleYPercent?: number;
  subtitleYPercent?: number;
  subtitlePositionMode?: SubtitlePositionMode;
  subtitleCenterYPercent?: number;
  selectedClips: ViralClip[];
  // Background Music
  bgmEnabled?: boolean;
  bgmFilePath?: string;
  bgmFileName?: string;
  bgmVolume?: number; // 0 to 100%
  bgmStartOffset?: number; // seconds from start of audio track
  // Hook SFX
  hookSfxEnabled?: boolean;
  hookSfxFilePath?: string;
  hookSfxFileName?: string;
  hookSfxVolume?: number; // 0 to 150%
  // Raw Audio / Voice Boost
  originalAudioVolume?: number; // 0 to 200%
  originalAudioPitch?: number; // semitones (-12 to +12)
  // Video Color Grading
  colorBrightness?: number; // -100 to 100
  colorContrast?: number; // -100 to 100
  colorSaturation?: number; // -100 to 100
  colorHue?: number; // -180 to 180 degrees
  colorTemperature?: number; // -100 (cool) to 100 (warm)
  // Custom Facecam Overlay (user's own camera/avatar)
  facecamOverlayEnabled?: boolean;
  facecamOverlayFilePath?: string;
  facecamOverlayFileName?: string;
  facecamOverlayUrl?: string;
  facecamOverlayMediaType?: 'video' | 'image';
  facecamOverlayPosition?: string; // 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right' | 'center'
  facecamOverlaySize?: number; // 8 to 70 (% of canvas width)
  facecamOverlayOpacity?: number; // 10 to 100%
  facecamOverlayShape?: 'square' | 'circle';
  facecamOverlayMirror?: boolean;
  // Voice Over (own narration audio)
  voiceoverEnabled?: boolean;
  voiceoverFilePath?: string;
  voiceoverFileName?: string;
  voiceoverUrl?: string;
  voiceoverVolume?: number; // 0 to 200%
  voiceoverDelay?: number; // seconds before voiceover starts
  voiceoverPitch?: number; // semitones (-12 to +12)
  voiceoverLoop?: boolean;
  // Watermark
  watermarkEnabled?: boolean;
  watermarkType?: 'image' | 'text';
  watermarkFilePath?: string;
  watermarkUrl?: string;
  watermarkText?: string;
  watermarkSize?: number; // 5 to 50%
  watermarkOpacity?: number; // 10 to 100%
  watermarkX?: number; // 0 to 100%
  watermarkY?: number; // 0 to 100%
  // Hardware Acceleration / Video Encoder
  hardwareAccel?: HardwareAccelOption;
  // Eye-catching thumbnails generated alongside each render
  thumbnailEnabled?: boolean;
  thumbnailFormat?: ThumbnailFormat;
  thumbnailStyle?: ThumbnailStyle;
  // Multi-Segment Merged Highlight Video
  renderMode?: 'separate' | 'merged';
  compilationTitle?: string;
}

export interface RenderClipStatus {
  clip_index: number;
  title: string;
  base_title?: string;
  status: 'pending' | 'downloading' | 'transcribing' | 'tracking' | 'rendering' | 'completed' | 'error';
  progress_percent: number;
  download_url?: string;
  thumbnail_url?: string;
  thumbnail_path?: string;
  error_message?: string;
  error?: string;
}

export interface BatchRenderProgress {
  batch_id: string;
  total_clips: number;
  current_clip_index: number;
  overall_status: 'running' | 'completed' | 'error';
  zip_url?: string;
  error_message?: string;
  warning_message?: string;
  clips: RenderClipStatus[];
}
