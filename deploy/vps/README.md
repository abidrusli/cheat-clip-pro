# Deploy ke VPS (Debian 12 direkomendasikan)

Panduan ini membuat backend + frontend 1.0.6 jalan 24/7 di VPS, sehingga HP cukup membuka APK dan PC tidak perlu menyala.

## Alamat contoh

- IP VPS: `202.155.16.44`
- Domain: `sinyalrdm.id`
- Subdomain yang disarankan: `klip.sinyalrdm.id`

> `sinyalrdm.id/sinyalrdm.id` bukan format DNS. Yang benar adalah A record `klip` → `202.155.16.44`.

## 1. Cek spesifikasi VPS

```bash
nproc
free -h
df -h /
cat /etc/os-release
```

Minimal: **2 vCPU / 4 GB RAM / 30 GB SSD**. Paket Rumahweb XS (1 vCPU / 512 MB / 10 GB) **tidak cukup**. Debian 10 juga sudah EOL; reinstall ke **Debian 12** sangat disarankan.

## 2. Set DNS

Di pengaturan DNS domain:

| Type | Name | Value |
| --- | --- | --- |
| A | `klip` | `202.155.16.44` |

Tunggu propagate, cek dengan:

```bash
nslookup klip.sinyalrdm.id 8.8.8.8
```

## 3. Upload repo ke VPS

```bash
apt-get update && apt-get install -y git
git clone <REPO_URL> /opt/kliper-pro
cd /opt/kliper-pro
```

## 4. Isi kredensial

```bash
cp .env.example .env
nano .env
```

Isi minimal:

```env
GEMINI_API_KEY=API_KEY_GEMINI_ANDA
DOMAIN=klip.sinyalrdm.id
ALLOWED_ORIGINS=https://klip.sinyalrdm.id
MEM_LIMIT=3g
```

Biarkan `ACCESS_TOKEN=` kosong; script deploy akan membuat kode akses acak otomatis.

## 5. Deploy

```bash
bash deploy/vps/deploy.sh
```

Script akan:
- install Docker, Nginx, Certbot;
- membuat/mengisi `ACCESS_TOKEN` bila kosong;
- menulis config Nginx dengan batas upload 4 GB;
- build + start container di `127.0.0.1:8000`;
- memasang SSL Let's Encrypt bila DNS sudah aktif.

## 6. Pakai di APK

Buka APK → **Ganti Server** → masukkan:

```text
https://klip.sinyalrdm.id
```

Ketika halaman login muncul, masukkan **kode akses** yang dicetak script deploy. Kode ini berbeda dari API key Gemini.

## Perintah berguna

```bash
# Status
docker compose --env-file ./.env -f deploy/vps/docker-compose.yml ps

# Log
docker compose --env-file ./.env -f deploy/vps/docker-compose.yml logs -f

# Restart
docker compose --env-file ./.env -f deploy/vps/docker-compose.yml restart

# Update setelah git pull
git pull
docker compose --env-file ./.env -f deploy/vps/docker-compose.yml up -d --build

# Ganti kode akses
nano .env   # isi ACCESS_TOKEN=...
docker compose --env-file ./.env -f deploy/vps/docker-compose.yml up -d

# SSL belum terpasang / perlu diperbarui
certbot --nginx -d klip.sinyalrdm.id
```

## Catatan keamanan

- Jangan pernah mempublikasikan `GEMINI_API_KEY` atau `ACCESS_TOKEN`.
- Tanpa `ACCESS_TOKEN`, siapa pun yang tahu alamat bisa memakai API, upload file, dan menghabiskan kuota Gemini.
- Port `8000` sengaja hanya dibuka di `127.0.0.1`; akses publik lewat Nginx/HTTPS.
