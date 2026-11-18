import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.resolve(__dirname, '..');
const projectRoot = path.resolve(desktopDir, '..');
const specFile = path.join(desktopDir, 'pyinstaller', 'backend.spec');
const distPath = path.join(desktopDir, 'pyinstaller', 'dist');
const workPath = path.join(desktopDir, 'pyinstaller', 'build');
const outputDir = path.join(distPath, 'cheat-clip-backend');
const toolsCache = path.join(desktopDir, 'pyinstaller', 'tools');

const FFMPEG_ZIP_URL = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip';
const WHISPER_ZIP_URL = 'https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-blas-bin-x64.zip';
const WHISPER_MODEL_URL = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base-q8_0.bin';

function findPython() {
  const candidates = [
    path.join(projectRoot, 'venv', 'Scripts', 'python.exe'),
    path.join(projectRoot, '.venv', 'Scripts', 'python.exe'),
    path.join(projectRoot, 'venv', 'bin', 'python'),
    path.join(projectRoot, '.venv', 'bin', 'python'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function whereFirst(command) {
  const tool = process.platform === 'win32' ? 'where' : 'which';
  try {
    const out = execFileSync(tool, [command], { encoding: 'utf8' });
    const first = out
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)[0];
    return first ? fs.realpathSync(first) : null;
  } catch {
    return null;
  }
}

function downloadFile(url, dest) {
  if (fs.existsSync(dest) && fs.statSync(dest).size > 0) return;
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  console.log(`→ Downloading ${path.basename(dest)}...`);
  const curl = whereFirst('curl') || (process.platform === 'win32' ? 'curl.exe' : 'curl');
  const result = spawnSync(curl, ['-L', '--fail', '--retry', '3', '-o', dest, url], {
    stdio: 'inherit',
  });
  if (result.status !== 0) throw new Error(`Failed to download ${url}`);
}

function extractZip(zip, dest) {
  if (fs.existsSync(dest)) fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });
  if (process.platform === 'win32') {
    const ps = [
      '-NoProfile',
      '-Command',
      `Expand-Archive -LiteralPath '${zip}' -DestinationPath '${dest}' -Force`,
    ];
    const result = spawnSync('powershell', ps, { stdio: 'inherit' });
    if (result.status !== 0) throw new Error(`Failed to extract ${zip}`);
  } else {
    const result = spawnSync('tar', ['-xf', zip, '-C', dest], { stdio: 'inherit' });
    if (result.status !== 0) throw new Error(`Failed to extract ${zip}`);
  }
}

function findFileRecursive(root, name) {
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) {
      const found = findFileRecursive(full, name);
      if (found) return found;
    } else if (entry.name.toLowerCase() === name.toLowerCase()) {
      return full;
    }
  }
  return null;
}

function stageFfmpeg() {
  const zip = path.join(toolsCache, 'ffmpeg-release-essentials.zip');
  const dir = path.join(toolsCache, 'ffmpeg-essentials');
  downloadFile(FFMPEG_ZIP_URL, zip);
  extractZip(zip, dir);

  const ffmpeg = findFileRecursive(dir, process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg');
  const ffprobe = findFileRecursive(dir, process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe');
  if (!ffmpeg || !ffprobe) throw new Error('FFmpeg essentials archive is missing ffmpeg/ffprobe');
  return { ffmpeg, ffprobe };
}

function stageWhisperCpp() {
  const zip = path.join(toolsCache, 'whisper-blas-bin-x64.zip');
  const dir = path.join(toolsCache, 'whispercpp');
  const model = path.join(dir, 'ggml-base-q8_0.bin');

  downloadFile(WHISPER_ZIP_URL, zip);
  extractZip(zip, dir);
  downloadFile(WHISPER_MODEL_URL, model);

  const cli = findFileRecursive(dir, process.platform === 'win32' ? 'whisper-cli.exe' : 'whisper-cli');
  if (!cli) throw new Error('whisper.cpp archive is missing whisper-cli');
  return { cliDir: path.dirname(cli), cli, model };
}

function copyYtDlp(targetDir) {
  const copied = [];
  const resolved = whereFirst('yt-dlp');
  if (!resolved) {
    console.warn('⚠ Could not find "yt-dlp" on PATH. The app will require it to be installed.');
    return copied;
  }
  const sourceDir = path.dirname(resolved);
  const files = [path.basename(resolved)];
  for (const entry of fs.readdirSync(sourceDir)) {
    if (/^yt-dlp\./i.test(entry) || /^yt_dlp/i.test(entry)) {
      if (!files.includes(entry)) files.push(entry);
    }
  }
  for (const file of files) {
    const src = path.join(sourceDir, file);
    const dest = path.join(targetDir, file);
    if (fs.existsSync(src) && fs.statSync(src).isFile()) {
      fs.copyFileSync(src, dest);
      copied.push(file);
    }
  }
  return copied;
}

function bundleRuntimeTools() {
  if (!fs.existsSync(outputDir)) {
    throw new Error(`Backend output folder not found: ${outputDir}`);
  }

  const ffmpegTools = stageFfmpeg();
  const whisper = stageWhisperCpp();
  const copied = [];

  // Small essentials FFmpeg build: libass/subtitles + HW encoders, ~100 MB each
  // instead of the ~217 MB full build.
  for (const [src, name] of [
    [ffmpegTools.ffmpeg, process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg'],
    [ffmpegTools.ffprobe, process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe'],
  ]) {
    fs.copyFileSync(src, path.join(outputDir, name));
    copied.push(name);
  }

  // whisper.cpp CLI + its DLLs live in their own folder next to the backend.
  const whisperOut = path.join(outputDir, 'whispercpp');
  fs.mkdirSync(whisperOut, { recursive: true });
  for (const entry of fs.readdirSync(whisper.cliDir)) {
    const src = path.join(whisper.cliDir, entry);
    const isCli = path.resolve(src) === path.resolve(whisper.cli);
    const isDll = path.extname(entry).toLowerCase() === '.dll';
    if (isCli || isDll) {
      fs.copyFileSync(src, path.join(whisperOut, entry));
      copied.push(`whispercpp/${entry}`);
    }
  }

  const modelOut = path.join(outputDir, 'backend', 'models', 'whisper', 'ggml-base-q8_0.bin');
  fs.mkdirSync(path.dirname(modelOut), { recursive: true });
  fs.copyFileSync(whisper.model, modelOut);
  copied.push('backend/models/whisper/ggml-base-q8_0.bin');

  copied.push(...copyYtDlp(outputDir));

  console.log(`→ Bundled runtime tools: ${copied.length} files`);
  fs.writeFileSync(
    path.join(outputDir, 'bundled-tools.json'),
    JSON.stringify({
      ffmpeg: process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg',
      ffprobe: process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe',
      ytDlp: 'yt-dlp',
      whisperCli: path.join('whispercpp', process.platform === 'win32' ? 'whisper-cli.exe' : 'whisper-cli'),
      whisperModel: path.join('backend', 'models', 'whisper', 'ggml-base-q8_0.bin'),
    }, null, 2),
  );

  // Sanity-check the smaller FFmpeg still exposes the libass subtitle filter.
  try {
    const ffmpegExe = path.join(outputDir, process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg');
    const filters = execFileSync(ffmpegExe, ['-hide_banner', '-filters'], { encoding: 'utf8' });
    console.log(filters.includes(' subtitles ')
      ? '✓ Bundled FFmpeg supports the subtitles filter'
      : '✗ Bundled FFmpeg may lack libass (subtitles filter)');
  } catch {
    // Non-fatal
  }
}

function main() {
  const python = findPython();
  console.log(`→ Using Python: ${python}`);

  if (!fs.existsSync(specFile)) {
    throw new Error(`PyInstaller spec not found: ${specFile}`);
  }

  const hasPyInstaller = spawnSync(python, ['-m', 'PyInstaller', '--version'], {
    stdio: 'ignore',
  }).status === 0;

  if (!hasPyInstaller) {
    console.log('→ Installing PyInstaller into the project environment...');
    const install = spawnSync(python, ['-m', 'pip', 'install', 'pyinstaller'], {
      stdio: 'inherit',
    });
    if (install.status !== 0) {
      throw new Error('Failed to install PyInstaller.');
    }
  }

  // Remove the previous backend completely so no stale PyTorch/Whisper files
  // survive into the new lightweight build.
  if (fs.existsSync(outputDir)) {
    fs.rmSync(outputDir, { recursive: true, force: true });
  }

  console.log('→ Building backend executable (PyInstaller onedir, no PyTorch)...');
  const build = spawnSync(
    python,
    [
      '-m',
      'PyInstaller',
      '--noconfirm',
      '--clean',
      '--distpath',
      distPath,
      '--workpath',
      workPath,
      specFile,
    ],
    { cwd: projectRoot, stdio: 'inherit' },
  );

  if (build.status !== 0) {
    throw new Error(`PyInstaller build failed with exit code ${build.status}.`);
  }

  console.log('→ Bundling lightweight FFmpeg + whisper.cpp...');
  bundleRuntimeTools();

  console.log(`✓ Backend built at: ${outputDir}`);
}

try {
  main();
} catch (err) {
  console.error(`✗ ${err.message || err}`);
  process.exit(1);
}
