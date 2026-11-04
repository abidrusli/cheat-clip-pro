import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..', '..');

const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';

console.log('▶ Building frontend (vite)...');
const result = spawnSync(`${npmCmd} run build`, {
  cwd: projectRoot,
  stdio: 'inherit',
  // Run through a shell so the Windows .cmd shim works (Node >= 18.20 blocks it otherwise).
  shell: true,
});

if (result.status !== 0) {
  console.error('✖ Frontend build failed.');
  process.exit(result.status ?? 1);
}

console.log('✓ Frontend built into dist/');
