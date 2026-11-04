import { FFmpeg } from '@ffmpeg/ffmpeg';
import { fetchFile, toBlobURL } from '@ffmpeg/util';

let ffmpegInstance: FFmpeg | null = null;
let isLoaded = false;
let loadPromise: Promise<FFmpeg> | null = null;

export interface ClientRenderOptions {
  videoSourceUrl: string; // URL or Blob URL of the source clip
  startTime?: number;
  endTime?: number;
  aspectRatio: '9:16' | '1:1' | '16:9' | '4:5';
  backgroundStyle: 'blur' | 'black' | 'fit' | 'crop';
  titleText?: string;
  titlePosition?: 'top' | 'center' | 'bottom';
  subtitles?: Array<{ start: number; end: number; text: string }>;
  fileName?: string;
  originalAudioPitch?: number;
  colorBrightness?: number;
  colorContrast?: number;
  colorSaturation?: number;
  colorHue?: number;
  colorTemperature?: number;
  onProgress?: (percent: number, stage: string) => void;
}

/**
 * Initializes and loads FFmpeg WebAssembly instance in browser worker with fallback.
 */
export async function getFFmpeg(onLoadProgress?: (ratio: number) => void): Promise<FFmpeg> {
  if (ffmpegInstance && isLoaded) {
    return ffmpegInstance;
  }

  if (loadPromise) {
    return loadPromise;
  }

  loadPromise = (async () => {
    const ffmpeg = new FFmpeg();

    ffmpeg.on('log', ({ message }) => {
      console.debug('[FFmpeg-WASM]', message);
    });

    ffmpeg.on('progress', ({ progress }) => {
      const pct = Math.min(100, Math.max(0, Math.round(progress * 100)));
      if (onLoadProgress) {
        onLoadProgress(pct);
      }
    });

    const baseURL = 'https://unpkg.com/@ffmpeg/core@0.12.6/dist/esm';
    
    try {
      await ffmpeg.load({
        coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, 'text/javascript'),
        wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, 'application/wasm'),
      });
      isLoaded = true;
      ffmpegInstance = ffmpeg;
      return ffmpeg;
    } catch (err) {
      console.warn('Primary ESM FFmpeg WASM load failed, trying standard core fallback...', err);
      const fallbackBase = 'https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.6/dist/umd';
      await ffmpeg.load({
        coreURL: await toBlobURL(`${fallbackBase}/ffmpeg-core.js`, 'text/javascript'),
        wasmURL: await toBlobURL(`${fallbackBase}/ffmpeg-core.wasm`, 'application/wasm'),
      });
      isLoaded = true;
      ffmpegInstance = ffmpeg;
      return ffmpeg;
    }
  })();

  return loadPromise;
}

/**
 * Builds an ffmpeg audio filter that shifts pitch while preserving duration.
 * Mirrors the backend `_pitch_shift_filter` so both engines sound the same.
 */
function buildPitchFilter(semitones?: number): string {
  const st = clampNum(semitones, -12, 12);
  if (Math.abs(st) < 0.05) return '';
  const ratio = Math.pow(2, st / 12);
  const parts = ['aresample=48000', `asetrate=${Math.round(48000 * ratio)}`, 'aresample=48000'];
  let tempo = 1 / ratio;
  while (tempo > 2) { parts.push('atempo=2.0'); tempo /= 2; }
  while (tempo < 0.5) { parts.push('atempo=0.5'); tempo *= 2; }
  parts.push(`atempo=${tempo.toFixed(6)}`);
  return parts.join(',');
}

function clampNum(value: number | undefined, low: number, high: number): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(low, Math.min(high, n));
}

/**
 * Builds an ffmpeg video filter for color grading. Mirrors the backend helper.
 */
function buildColorFilter(options: ClientRenderOptions): string {
  const b = clampNum(options.colorBrightness, -100, 100);
  const c = clampNum(options.colorContrast, -100, 100);
  const s = clampNum(options.colorSaturation, -100, 100);
  const h = clampNum(options.colorHue, -180, 180);
  const t = clampNum(options.colorTemperature, -100, 100);
  const parts: string[] = [];
  if (Math.abs(b) > 0.01 || Math.abs(c) > 0.01 || Math.abs(s) > 0.01) {
    parts.push(
      `eq=brightness=${(b / 200).toFixed(4)}:` +
      `contrast=${(1 + c / 200).toFixed(4)}:` +
      `saturation=${(1 + s / 100).toFixed(4)}`
    );
  }
  if (Math.abs(h) > 0.01) {
    parts.push(`hue=h=${h.toFixed(2)}`);
  }
  if (Math.abs(t) > 0.01) {
    const rs = (t / 100) * 0.15;
    const bs = -(t / 100) * 0.15;
    parts.push(`colorbalance=rs=${rs.toFixed(4)}:gs=0.0000:bs=${bs.toFixed(4)}`);
  }
  return parts.join(',');
}

/**
 * Renders a video clip directly in the client's browser using WebAssembly.
 * Fully offloads CPU computation from the server.
 */
export async function renderClipClientSide(options: ClientRenderOptions): Promise<Blob> {
  const {
    videoSourceUrl,
    startTime = 0,
    endTime,
    aspectRatio = '9:16',
    backgroundStyle = 'blur',
    onProgress
  } = options;

  if (onProgress) onProgress(5, 'Loading Client-Side Engine (WASM)...');
  const ffmpeg = await getFFmpeg((ratio) => {
    if (onProgress) onProgress(Math.min(25, 5 + Math.round(ratio * 0.2)), 'Initializing WASM core...');
  });

  if (onProgress) onProgress(28, 'Fetching video stream to browser memory...');
  const inputData = await fetchFile(videoSourceUrl);
  await ffmpeg.writeFile('input.mp4', inputData);

  // Construct FFmpeg filters based on aspect ratio and background style
  let filterStr = '';
  let targetWidth = 1080;
  let targetHeight = 1920;

  if (aspectRatio === '9:16') {
    targetWidth = 1080;
    targetHeight = 1920;
    if (backgroundStyle === 'blur') {
      filterStr = `[0:v]scale=${targetWidth}:${targetHeight}:force_original_aspect_ratio=increase,crop=${targetWidth}:${targetHeight},gblur=sigma=20[bg];[0:v]scale=${targetWidth}:${targetHeight}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v]`;
    } else if (backgroundStyle === 'black') {
      filterStr = `[0:v]scale=${targetWidth}:${targetHeight}:force_original_aspect_ratio=decrease,pad=${targetWidth}:${targetHeight}:(ow-iw)/2:(oh-ih)/2:black[v]`;
    } else {
      // Direct center crop
      filterStr = `[0:v]scale=ih*9/16:ih,scale=${targetWidth}:${targetHeight}[v]`;
    }
  } else if (aspectRatio === '1:1') {
    targetWidth = 1080;
    targetHeight = 1080;
    filterStr = `[0:v]scale=${targetWidth}:${targetHeight}:force_original_aspect_ratio=decrease,pad=${targetWidth}:${targetHeight}:(ow-iw)/2:(oh-ih)/2:black[v]`;
  } else if (aspectRatio === '4:5') {
    targetWidth = 1080;
    targetHeight = 1350;
    filterStr = `[0:v]scale=${targetWidth}:${targetHeight}:force_original_aspect_ratio=decrease,pad=${targetWidth}:${targetHeight}:(ow-iw)/2:(oh-ih)/2:black[v]`;
  } else {
    // 16:9 Landscape
    targetWidth = 1920;
    targetHeight = 1080;
    filterStr = `[0:v]scale=${targetWidth}:${targetHeight}:force_original_aspect_ratio=decrease,pad=${targetWidth}:${targetHeight}:(ow-iw)/2:(oh-ih)/2:black[v]`;
  }

  // Apply color grading to the source before scaling/layout.
  const colorFilter = buildColorFilter(options);
  if (colorFilter) {
    filterStr = filterStr.replace(/\[0:v\]/g, `[0:v]${colorFilter},`);
  }

  const outputName = 'output.mp4';
  const ffmpegArgs: string[] = ['-i', 'input.mp4'];

  if (startTime > 0) {
    ffmpegArgs.unshift('-ss', startTime.toFixed(2));
  }
  if (endTime && endTime > startTime) {
    ffmpegArgs.push('-t', (endTime - startTime).toFixed(2));
  }

  ffmpegArgs.push(
    '-filter_complex', filterStr,
    '-map', '[v]',
    '-map', '0:a?',
  );

  const pitchFilter = buildPitchFilter(options.originalAudioPitch);
  if (pitchFilter) {
    ffmpegArgs.push('-af', pitchFilter);
  }

  ffmpegArgs.push(
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-crf', '24',
    '-c:a', 'aac',
    '-b:a', '128k',
    '-movflags', '+faststart',
    outputName
  );

  ffmpeg.on('progress', ({ progress }) => {
    const pct = Math.min(98, 30 + Math.round(progress * 68));
    if (onProgress) {
      onProgress(pct, `Rendering on your device GPU/CPU (${pct}%)...`);
    }
  });

  if (onProgress) onProgress(35, 'Encoding vertical MP4 on client...');
  await ffmpeg.exec(ffmpegArgs);

  if (onProgress) onProgress(99, 'Extracting rendered MP4 file...');
  const outputData = await ffmpeg.readFile(outputName);
  const blob = new Blob([outputData as any], { type: 'video/mp4' });

  // Cleanup virtual files to free WASM memory
  try {
    await ffmpeg.deleteFile('input.mp4');
    await ffmpeg.deleteFile(outputName);
  } catch {
    // Ignore cleanup
  }

  if (onProgress) onProgress(100, 'Rendering Complete!');
  return blob;
}

/**
 * Helper to trigger automatic download of a Blob file in the user's browser.
 */
export function triggerBrowserDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename.endsWith('.mp4') ? filename : `${filename}.mp4`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
