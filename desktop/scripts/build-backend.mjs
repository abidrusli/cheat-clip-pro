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

function copyExternalTools(python) {
  const targetDir = outputDir;
  if (!fs.existsSync(targetDir)) {
    throw new Error(`Backend output folder not found: ${targetDir}`);
  }

  const copied = [];
  const copyWithSiblings = (name, siblings = []) => {
    const resolved = whereFirst(name);
    if (!resolved) {
      console.warn(`⚠ Could not find "${name}" on PATH. The app will require it to be installed.`);
      return;
    }
    const sourceDir = path.dirname(resolved);
    const files = [path.basename(resolved)];
    for (const sibling of siblings) {
      const siblingPath = path.join(sourceDir, sibling);
      if (fs.existsSync(siblingPath)) files.push(sibling);
    }
    // Also copy any shared-library siblings (DLLs on Windows, .so on Linux/macOS).
    for (const entry of fs.readdirSync(sourceDir)) {
      const ext = path.extname(entry).toLowerCase();
      if ((ext === '.dll' || ext === '.so' || ext.startsWith('.so.')) && !files.includes(entry)) {
        files.push(entry);
      }
    }
    for (const file of files) {
      const src = path.join(sourceDir, file);
      const dest = path.join(targetDir, file);
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, dest);
        copied.push(file);
      }
    }
  };

  copyWithSiblings('ffmpeg', ['ffprobe.exe', 'ffprobe']);
  copyWithSiblings('ffprobe');
  copyWithSiblings('yt-dlp', ['yt-dlp.exe']);

  console.log(`✓ Bundled external tools: ${copied.join(', ') || '(none)'}`);

  // Emit a small manifest so the backend can prefer its bundled binaries explicitly.
  fs.writeFileSync(
    path.join(targetDir, 'bundled-tools.json'),
    JSON.stringify({ ffmpeg: 'ffmpeg', ffprobe: 'ffprobe', ytDlp: 'yt-dlp' }, null, 2)
  );

  // Sanity-check the bundled ffmpeg exposes the libass subtitle filter.
  try {
    const ffmpegExe = path.join(targetDir, process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg');
    if (fs.existsSync(ffmpegExe)) {
      const filters = execFileSync(ffmpegExe, ['-hide_banner', '-filters'], { encoding: 'utf8' });
      console.log(filters.includes(' subtitles ') ? '✓ Bundled ffmpeg supports the subtitles filter' : '⚠ Bundled ffmpeg may lack libass (subtitles filter)');
    }
  } catch {
    // Non-fatal
  }
}

function stageWhisperModel() {
  const modelDir = path.join(projectRoot, 'backend', 'models', 'whisper');
  const target = path.join(modelDir, 'base.pt');
  if (fs.existsSync(target)) {
    console.log(`✓ Whisper model already staged: ${target}`);
    return;
  }

  const candidates = [
    process.env.WHISPER_MODEL_PATH,
    path.join(process.env.USERPROFILE || '', '.cache', 'whisper', 'base.pt'),
    path.join(process.env.LOCALAPPDATA || '', 'whisper', 'base.pt'),
  ].filter(Boolean);

  const source = candidates.find((candidate) => fs.existsSync(candidate));
  if (!source) {
    console.warn('⚠ Whisper base.pt was not found locally. The desktop app will download it on first use.');
    return;
  }

  fs.mkdirSync(modelDir, { recursive: true });
  fs.copyFileSync(source, target);
  console.log(`✓ Staged Whisper model: ${source} -> ${target}`);
}

function main() {
  const python = findPython();
  console.log(`▶ Using Python: ${python}`);

  if (!fs.existsSync(specFile)) {
    throw new Error(`PyInstaller spec not found: ${specFile}`);
  }

  stageWhisperModel();

  // Ensure PyInstaller is available in the chosen interpreter.
  const hasPyInstaller = spawnSync(python, ['-m', 'PyInstaller', '--version'], {
    stdio: 'ignore',
  }).status === 0;

  if (!hasPyInstaller) {
    console.log('▶ Installing PyInstaller into the project environment...');
    const install = spawnSync(python, ['-m', 'pip', 'install', 'pyinstaller'], {
      stdio: 'inherit',
    });
    if (install.status !== 0) {
      throw new Error('Failed to install PyInstaller.');
    }
  }

  console.log('▶ Building backend executable (PyInstaller onedir)...');
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
    { cwd: projectRoot, stdio: 'inherit' }
  );

  if (build.status !== 0) {
    throw new Error(`PyInstaller build failed with exit code ${build.status}.`);
  }

  console.log('▶ Bundling ffmpeg / ffprobe / yt-dlp...');
  copyExternalTools(python);

  console.log(`✓ Backend built at: ${outputDir}`);
}

try {
  main();
} catch (err) {
  console.error(`✖ ${err.message || err}`);
  process.exit(1);
}
