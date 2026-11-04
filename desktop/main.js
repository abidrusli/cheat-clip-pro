const { app, BrowserWindow, shell, dialog } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const http = require('node:http');

const isDev = !app.isPackaged;

let mainWindow = null;
let backendProcess = null;
let backendPort = null;
let backendLogStream = null;
let isQuitting = false;
let dataRootDir = null;

/**
 * Resolve the writable data root.
 * For the portable build (electron-builder "portable" target) data is kept next to
 * the executable; otherwise it uses the per-user application data directory.
 */
function getDataRoot() {
  if (dataRootDir) return dataRootDir;
  const portableDir = process.env.PORTABLE_EXECUTABLE_DIR;
  if (portableDir) {
    const candidate = path.join(portableDir, 'SinyalAbidnet Kliper Pro Data');
    try {
      fs.mkdirSync(candidate, { recursive: true });
      dataRootDir = candidate;
      return dataRootDir;
    } catch {
      // Fall back to userData if the portable location is not writable.
    }
  }
  dataRootDir = app.getPath('userData');
  return dataRootDir;
}

function backendLogPath() {
  return path.join(getDataRoot(), 'logs', 'backend.log');
}

// Redirect all user data (including Chromium storage and the single-instance lock)
// into the resolved root so the portable build is fully self-contained and can run
// alongside an installed copy.
try {
  app.setPath('userData', getDataRoot());
} catch {
  // Fall back to the default userData directory.
}

/**
 * Resolve the location of the backend executable and the built web assets
 * for both development (running from source) and a packaged installer.
 */
function resolveLayout() {
  const projectRoot = path.resolve(__dirname, '..');
  if (isDev) {
    const backendDir = path.join(__dirname, 'pyinstaller', 'dist', 'cheat-clip-backend');
    return {
      backendExe: path.join(backendDir, 'cheat-clip-backend.exe'),
      backendDir,
      webDir: path.join(projectRoot, 'dist'),
    };
  }
  const backendDir = path.join(process.resourcesPath, 'backend');
  return {
    backendExe: path.join(backendDir, 'cheat-clip-backend.exe'),
    backendDir,
    webDir: path.join(process.resourcesPath, 'web'),
  };
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function startBackend(port) {
  const { backendExe, backendDir, webDir } = resolveLayout();

  if (!fs.existsSync(backendExe)) {
    throw new Error(
      `Backend executable not found at:\n${backendExe}\n\n` +
        'Build it first with "npm run build:backend".'
    );
  }

  const dataRoot = getDataRoot();
  const dataDir = path.join(dataRoot, 'data');
  fs.mkdirSync(dataDir, { recursive: true });

  const logsDir = path.join(dataRoot, 'logs');
  fs.mkdirSync(logsDir, { recursive: true });
  backendLogStream = fs.createWriteStream(backendLogPath(), { flags: 'a' });

  const env = {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(port),
    PYTHONUNBUFFERED: '1',
    PYTHONIOENCODING: 'utf-8',
    CHEAT_CLIP_WEB_DIR: webDir,
    CHEAT_CLIP_DATA_DIR: dataDir,
    PATH: `${backendDir}${path.delimiter}${process.env.PATH || ''}`,
    Path: `${backendDir}${path.delimiter}${process.env.PATH || ''}`,
  };
  // Do not leak Electron's node-only switches into the Python child.
  delete env.ELECTRON_RUN_AS_NODE;

  backendLogStream.write(
    `\n===== ${new Date().toISOString()} starting backend on port ${port} =====\n`
  );

  backendProcess = spawn(backendExe, [], {
    cwd: backendDir,
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.on('error', (err) => {
    backendLogStream?.write(`[spawn error] ${err.stack || err}\n`);
  });

  const pipeToLog = (stream, prefix) => {
    stream.setEncoding('utf8');
    stream.on('data', (chunk) => backendLogStream?.write(`[${prefix}] ${chunk}`));
  };
  if (backendProcess.stdout) pipeToLog(backendProcess.stdout, 'out');
  if (backendProcess.stderr) pipeToLog(backendProcess.stderr, 'err');

  backendProcess.on('exit', (code, signal) => {
    backendLogStream?.write(`[exit] code=${code} signal=${signal}\n`);
    if (!isQuitting) {
      dialog.showErrorBox(
        'SinyalAbidnet Kliper Pro backend stopped',
        `The background service exited unexpectedly (code ${code}).\n` +
          `Logs: ${backendLogPath()}`
      );
      app.quit();
    }
  });
}

function backendHealthCheck(port) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: '127.0.0.1', port, path: '/api/health', timeout: 2000 },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(port, timeoutMs = 90000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await backendHealthCheck(port)) return true;
    if (!backendProcess || backendProcess.exitCode !== null) return false;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function killBackendTree() {
  if (!backendProcess || backendProcess.exitCode !== null) return;
  const pid = backendProcess.pid;
  if (process.platform === 'win32') {
    try {
      spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true });
    } catch {
      backendProcess.kill();
    }
  } else {
    backendProcess.kill('SIGTERM');
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1024,
    minHeight: 720,
    show: false,
    backgroundColor: '#0b0e14',
    title: 'SinyalAbidnet Kliper Pro',
    icon: path.join(__dirname, 'build-resources', 'icon.ico'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  return mainWindow;
}

async function bootstrap() {
  const { backendExe, webDir } = resolveLayout();
  const missing = [];
  if (!fs.existsSync(backendExe)) missing.push(`Backend: ${backendExe}`);
  if (!fs.existsSync(path.join(webDir, 'index.html'))) missing.push(`Web app: ${webDir}`);

  if (missing.length) {
    dialog.showErrorBox(
      'SinyalAbidnet Kliper Pro is not built yet',
      `Missing build artifacts:\n\n${missing.join('\n')}\n\nRun "npm run dist" inside the desktop folder.`
    );
    app.quit();
    return;
  }

  const win = createWindow();
  win.loadFile(path.join(__dirname, 'splash.html'));

  try {
    backendPort = await findFreePort();
    startBackend(backendPort);
  } catch (err) {
    dialog.showErrorBox('Failed to start SinyalAbidnet Kliper Pro', String(err.message || err));
    app.quit();
    return;
  }

  const ready = await waitForBackend(backendPort);
  if (!ready) {
    dialog.showErrorBox(
      'SinyalAbidnet Kliper Pro backend did not start',
      `The backend did not become ready in time.\n\n` +
        `Logs: ${backendLogPath()}`
    );
    app.quit();
    return;
  }

  win.loadURL(`http://127.0.0.1:${backendPort}/`);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(bootstrap);

  app.on('window-all-closed', () => {
    app.quit();
  });

  app.on('before-quit', () => {
    isQuitting = true;
    killBackendTree();
    backendLogStream?.end();
  });

  app.on('will-quit', () => {
    killBackendTree();
  });
}
