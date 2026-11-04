import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.resolve(__dirname, '..');
const releaseDir = path.join(desktopDir, 'release');
const sourceDir = path.join(releaseDir, 'win-unpacked');
const pkg = JSON.parse(fs.readFileSync(path.join(desktopDir, 'package.json'), 'utf8'));
const zipPath = path.join(releaseDir, `SinyalAbidnet-Kliper-Pro-${pkg.version}-win-x64.zip`);

if (!fs.existsSync(sourceDir)) {
  console.error(`✖ Packaged app not found at ${sourceDir}. Run "electron-builder --win dir" first.`);
  process.exit(1);
}

if (fs.existsSync(zipPath)) {
  fs.rmSync(zipPath, { force: true });
}

console.log(`▶ Creating portable ZIP: ${zipPath}`);

const script =
  `Compress-Archive -Path '${sourceDir}' -DestinationPath '${zipPath}' -CompressionLevel Optimal -Force`;

const result = spawnSync(
  'powershell.exe',
  ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
  { stdio: 'inherit' }
);

if (result.status !== 0 || !fs.existsSync(zipPath)) {
  console.error('✖ Failed to create the portable ZIP.');
  process.exit(result.status ?? 1);
}

const sizeMb = (fs.statSync(zipPath).size / (1024 * 1024)).toFixed(1);
console.log(`✓ Portable ZIP created (${sizeMb} MB): ${zipPath}`);
