#!/usr/bin/env bash
# Deploy SinyalAbidnet Kliper Pro ke VPS Debian 11/12 (Disarankan Debian 12).
# Jalankan dari root repo sebagai root: bash deploy/vps/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [ "$(id -u)" -ne 0 ]; then
  echo "❌ Jalankan sebagai root: sudo bash deploy/vps/deploy.sh"
  exit 1
fi

if [ ! -f docker-compose.yml ] || [ ! -f Dockerfile ]; then
  echo "❌ Jalankan script ini dari root repo SinyalAbidnet Kliper Pro."
  exit 1
fi

. /etc/os-release
OS_ID="${ID:-unknown}"
OS_MAJOR="${VERSION_ID%%.*}"

if [ "$OS_ID" = "debian" ] && [ "$OS_MAJOR" -lt 11 ] && [ "${FORCE_DEBIAN10:-0}" != "1" ]; then
  echo "❌ Debian $VERSION_ID sudah EOL dan repo Docker/Certbot bermasalah."
  echo "   Silakan reinstall VPS ke Debian 12 melalui panel Rumahweb, lalu jalankan ulang."
  echo "   Jika tetap memaksa: FORCE_DEBIAN10=1 bash deploy/vps/deploy.sh"
  exit 1
fi

echo "▶ Memasang paket sistem..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg nginx docker.io docker-compose-plugin \
  certbot python3-certbot-nginx

systemctl enable --now docker nginx

if [ ! -f .env ]; then
  echo "▶ Membuat .env dari template..."
  cp .env.example .env
fi

set -a
. ./.env
set +a

DOMAIN="${DOMAIN:-klip.sinyalrdm.id}"

if [ -z "${ACCESS_TOKEN:-}" ]; then
  ACCESS_TOKEN="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)"
  sed -i "s|^ACCESS_TOKEN=.*|ACCESS_TOKEN=${ACCESS_TOKEN}|" .env
  echo "============================================================"
  echo "✅ Kode akses baru dibuat: ${ACCESS_TOKEN}"
  echo "   Simpan kode ini. Dipakai di halaman /login.html di HP."
  echo "============================================================"
fi

if [ -z "${GEMINI_API_KEY:-}" ]; then
  echo "⚠ GEMINI_API_KEY masih kosong. Isi di .env sebelum analisis AI."
fi

echo "▶ Menulis konfigurasi Nginx untuk ${DOMAIN}..."
mkdir -p /var/www/certbot
sed "s|__DOMAIN__|${DOMAIN}|g" deploy/vps/nginx/http.conf.template \
  > /etc/nginx/sites-available/kliper
ln -sf /etc/nginx/sites-available/kliper /etc/nginx/sites-enabled/kliper
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "▶ Membangun & menjalankan container (ini bisa beberapa menit)..."
docker compose --env-file ./.env -f deploy/vps/docker-compose.yml up -d --build

echo "▶ Menunggu backend sehat..."
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "✅ Backend sehat."
    break
  fi
  if [ "$i" -eq 90 ]; then
    echo "❌ Backend tidak sehat. Cek: docker compose -f deploy/vps/docker-compose.yml logs -f"
    exit 1
  fi
  sleep 2
done

if getent hosts "$DOMAIN" >/dev/null 2>&1; then
  echo "▶ DNS ${DOMAIN} sudah mengarah ke VPS. Memasang SSL..."
  certbot --nginx -d "$DOMAIN" \
    --non-interactive --agree-tos -m "admin@${DOMAIN}" --redirect || \
    echo "⚠ Certbot gagal. Cek DNS/port 80, lalu ulangi: certbot --nginx -d ${DOMAIN}"
else
  echo "⚠ DNS ${DOMAIN} belum resolve ke VPS ini."
  echo "  Sementara aplikasi bisa dibuka lewat http://${DOMAIN} (setelah A record dibuat)."
  echo "  Setelah DNS aktif, jalankan: certbot --nginx -d ${DOMAIN}"
fi

echo
echo "============================================================"
echo "✅ Selesai."
echo "   Buka di HP : https://${DOMAIN}"
echo "   Kode akses: ${ACCESS_TOKEN}"
echo "   Ganti server di APK → https://${DOMAIN}"
echo "============================================================"
