# 🎬 SinyalAbidnet Kliper Pro

> **AI Powered Auto Clipper — Turn long YouTube, Google Drive, Facebook, Threads, and uploaded videos into viral TikToks, Shorts, and Reels with animated subtitles, face centering, and music in minutes.**

---

## ⚡ Quick Start & Setup

Follow these steps to set up and run SinyalAbidnet Kliper Pro locally on **Windows**, **macOS**, or **Linux**.

### Step 1: Prerequisites

Make sure you have the following installed:

1. **[Git](https://git-scm.com/)**
   * **Windows:** `winget install Git.Git` or download from [git-scm.com](https://git-scm.com/)
   * **macOS:** `brew install git`
   * **Linux:** `sudo apt install git`
2. **[Node.js](https://nodejs.org/)** (v18 or newer)
   * Download from [nodejs.org](https://nodejs.org/) or install via your package manager.
3. **[Python](https://www.python.org/)** (v3.10 or newer)
   * **Windows:** Install from [python.org](https://www.python.org/downloads/) (make sure to check *"Add Python to PATH"* during setup) or from Microsoft Store.
   * **macOS:** `brew install python`
   * **Linux:** `sudo apt install python3 python3-pip python3-venv`
4. **FFmpeg & yt-dlp** (Required to download, slice, and render clips)
   * **Windows (PowerShell):**
     ```powershell
     winget install Gyan.FFmpeg
     winget install yt-dlp.yt-dlp
     ```
     *(Close and reopen your terminal after installing so Windows recognizes them)*
   * **macOS (Terminal):**
     ```bash
     brew install ffmpeg-full yt-dlp
     ```
      `ffmpeg-full` is required for the libass subtitle filter used by rendered captions.
   * **Linux:**
     ```bash
     sudo apt update && sudo apt install ffmpeg
     pip install yt-dlp
     ```

---

### Step 2: Clone the Repository

Open your terminal and clone the repository:

```bash
git clone https://github.com/galihjuansaputra/cheat-clip-pro.git
cd cheat-clip-pro
```

---

### Step 3: Install Dependencies

#### 1. Frontend Dependencies
```bash
npm install
```

#### 2. Backend Dependencies
We recommend setting up a Python virtual environment:

* **Windows:**
  ```powershell
  python -m venv venv
  venv\Scripts\activate
  pip install -r backend/requirements.txt
  ```

* **macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r backend/requirements.txt
  ```

---

### Step 4: Run the App

Launch both the frontend and backend servers concurrently:

```bash
npm run dev
```

* **Web App:** [`http://localhost:5173`](http://localhost:5173)
* **Backend API:** [`http://localhost:8000`](http://localhost:8000)
* **API Documentation:** [`http://localhost:8000/docs`](http://localhost:8000/docs)

---

## 🔄 Updating to the Latest Version

To update SinyalAbidnet Kliper Pro to the latest release:

```bash
git pull
npm install
pip install -r backend/requirements.txt
```
*(Make sure your virtual environment is activated if you created one)*

---

## 🔑 Free Google Gemini API Key (Takes 1 Minute)

SinyalAbidnet Kliper Pro uses Google's AI to find the best viral moments for free:
1. Go to **[Google AI Studio](https://aistudio.google.com/)** and sign in with any Google account.
2. Click **"Get API key"** (or **"Create API key"**).
3. Copy your key (starts with `AIzaSy...`).
4. Paste it into the **Gemini API Key** field in the app.

> 💡 **Tip:** You can also type `mock` in the API Key box to test out the app with sample data without an API key!

> ℹ️ **Gemini Free Tier:** kuota gratis hanya **20 request/hari per model**. Versi 1.0.6 sudah menggabungkan terjemahan dalam potongan besar dan langsung berhenti saat kuota habis, sehingga tidak boros request. Jika tetap habis, buat API key/project baru di Google AI Studio atau aktifkan billing.

---

## 🎯 How to Use

1. **Paste a YouTube URL** — Enter any podcast, stream, or video link.
2. **Choose Duration** — Pick `~15s` (fast hooks), `~30s` (standard shorts), or `~60s` (story clips).
3. **Click "Analyze Video"** — The AI finds the most exciting moments using YouTube audience retention data.
4. **Customize in Clip Studio** — Adjust your video style:
   * **Frame & Crop**: Fullscreen 9:16 vertical, square, or split-screen facecam.
   * **Face Tracking**: Automatically keeps the speaker in the center of the frame.
   * **Subtitles**: Choose viral animated karaoke caption styles and fonts.
   * **Branding & Audio**: Add your watermark logo, background music, and hook sound effects.
   * **Hardware Acceleration**: Choose your graphics card (NVIDIA, AMD, Intel) or CPU.
5. **Batch Render & Download** — Click **Batch Render**, then download all your finished videos together in one **.ZIP** file!

---

## ❓ Common Problems & Easy Fixes

### 1. "Failed to render video" or `The system cannot find the file specified`
* **Cause:** `ffmpeg` or `yt-dlp` is missing on your computer.
* **Fix:**
  * **Windows (PowerShell):**
    ```powershell
    winget install Gyan.FFmpeg
    winget install yt-dlp.yt-dlp
    ```
    *(Then close and reopen your terminal)*
  * **Mac (Terminal):**
    ```bash
    brew install ffmpeg-full yt-dlp
    ```
  * Or install directly via Python: `pip install yt-dlp`

### 2. `No such filter: 'subtitles'`
* **Cause:** FFmpeg was installed without the libass subtitle filter.
* **Fix (macOS):**
  ```bash
  brew install ffmpeg-full
  ```
  Restart the backend after installation. The app automatically prefers Homebrew's subtitle-capable `ffmpeg-full` binary.

### 3. "Sign in to confirm you're not a bot"
* **Cause:** YouTube blocks video downloads if too many requests are sent without logging in.
* **Fix:** Click the 🍪 **Cookies** button in the top navigation bar, export your YouTube cookies using a free browser extension (like *Get cookies.txt locally*), and paste them into the app.

### 4. Does this work on AMD graphics cards and Mac?
* **Yes!** SinyalAbidnet Kliper Pro automatically supports:
  * **NVIDIA** (`h264_nvenc`)
  * **AMD** (`h264_amf` on Radeon GPUs & Ryzen CPUs)
  * **Intel** (`h264_qsv` on Arc & UHD Graphics)
  * **Apple Mac & CPU Software** (`libx264` universal high-speed fallback)
* You can switch your preferred hardware acceleration encoder anytime in the Render Settings or History card.

---

## 📄 License

Distributed under the **MIT License**. Free for personal and commercial use!

---

## 🖥️ Desktop App (.exe)

SinyalAbidnet Kliper Pro can be packaged as a standalone Windows desktop application
(Electron shell + a frozen Python backend). The installer bundles Python
dependencies and FFmpeg, so end users do **not** need Python, Node.js, FFmpeg,
or yt-dlp installed.

> **Note:** The desktop build now bundles Whisper + PyTorch so Google Drive,
> Facebook/Threads, and uploaded videos can be transcribed locally without
> Python installed. The installer is larger because of the bundled Whisper
> `base` model; YouTube captions and manually supplied subtitles (`.srt` /
> `.txt`) still work without transcription.

### Prerequisites (build machine only)

* Node.js 18+ and Python 3.10+ (with the backend dependencies installed, see above)
* FFmpeg + yt-dlp available on `PATH` (they get copied into the installer)

### Build the installer

```bash
# 1. Install the desktop tooling (Electron + electron-builder)
npm run desktop:install

# 2. Build everything and produce the installer
npm run desktop:build
```

The installer is written to:

```
desktop/release/SinyalAbidnet-Kliper-Pro-Setup-<version>.exe
```

The build script downloads and caches the small FFmpeg **essentials** package
(~100 MB per binary, still with libass subtitles and hardware encoders) plus a
whisper.cpp BLAS build and `ggml-base-q8_0.bin`. These are copied next to the
frozen backend after PyInstaller runs. PyTorch and `openai-whisper` are
excluded from the bundle, so the backend stays lean and starts quickly. The
cached downloads live in `desktop/pyinstaller/tools/` and are git-ignored.

### Portable build (no installation)

You can also produce a single portable executable and a zipped folder that run
without installing anything:

```bash
npm run desktop:portable
```

Outputs in `desktop/release/`:

* `SinyalAbidnet-Kliper-Pro-<version>-portable.exe` — single self-extracting portable exe.
* `SinyalAbidnet-Kliper-Pro-<version>-win-x64.zip` — unzip and run `SinyalAbidnet Kliper Pro.exe`.
* `SinyalAbidnet-Kliper-Pro-Mobile-<version>.apk` — Android APK, also copied next to
  the installed/portable executable together with `start-mobile.bat`.

When launched from the portable exe, user data (temp clips, exports, uploads,
logs) is stored in a `SinyalAbidnet Kliper Pro Data` folder next to the executable so the
whole thing can live on a USB stick.

### Run without installing (development)

```bash
# Build the frontend + backend first
npm run desktop:install
cd desktop
npm run build:web
npm run build:backend

# Launch the desktop shell
npm start
```

### How it works

* `desktop/main.js` starts the frozen backend (`resources/backend/cheat-clip-backend.exe`)
  on a free local port and opens the UI in a native window.
* The backend serves both the API and the built web app, so it runs same-origin.
* Writable data (temp clips, exports, uploaded fonts) is stored in
  `%APPDATA%/SinyalAbidnet Kliper Pro/data`; logs go to `%APPDATA%/SinyalAbidnet Kliper Pro/logs`.
* In-app self-update/restart is disabled in the packaged build (there is no git
  checkout to pull from). Reinstall a newer installer to update.

### Performance tuning

Clip downloads run in parallel and can be tuned with environment variables:

* `CHEAT_CLIP_DOWNLOAD_CONCURRENCY` — number of clip segments downloaded at the
  same time (default `3`).
* `CHEAT_CLIP_YTDLP_CONCURRENCY` — concurrent fragments per yt-dlp download
  (default `8`).

Set them before launching the app, e.g. in PowerShell:
`$env:CHEAT_CLIP_DOWNLOAD_CONCURRENCY = "4"`. Very high values may trigger
YouTube throttling.

### Facecam overlay & Voice Over

Both features live in the Studio settings panel, in the audio/branding card list
(right below **Original Clip Voice Audio Boost**).

* **Your Facecam Avatar** — upload your own camera/avatar as an `.mp4`/`.mov`/
  `.webm` video or a `.png`/`.jpg`/`.webp` image. Choose position
  (top-left/top-right/bottom-left/bottom-right/center), size (8–70% of canvas
  width), opacity (10–100%), shape (square/circle) and mirror. The overlay is
  burned onto every rendered clip, which helps make the content unique.
* **Voice Over** — upload your own narration (`.mp3`/`.wav`/`.m4a`/`.aac`/`.ogg`/
  `.flac`). Controls: volume (0–200%), start delay (0–30 s), voice pitch
  (−12…+12 semitones) and loop-until-clip-ends. The narration is mixed with the
  original audio, BGM and SFX.
* **Original Voice Pitch** — a separate pitch slider inside *Original Clip Voice
  Audio Boost* shifts the pitch of the clip's original dialogue without changing
  its speed (−12…+12 semitones).

Pitch shifting uses `aresample` + `asetrate` + `atempo`, so it works with the
bundled FFmpeg without extra plugins.

### Output language (Bahasa Indonesia)

The **Output Language** selector under *Subtitles Source* defaults to
**Bahasa Indonesia**. Titles, summaries, captions, hashtags, key quotes and
burned-in subtitles are generated in Indonesian even when the source video and
transcript are English. The transcript is translated first, then the AI analysis
runs on the translated lines, so the final clip content stays consistent.

Choose **Follow Video** to keep the original spoken language. The selection is
saved locally and included in analysis cache/history keys, so switching languages
never mixes cached English and Indonesian results.

### Audio uploads (BGM, Voice Over, Hook SFX)

BGM, voice-over and hook SFX accept `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`,
`.opus`, `.oga`, `.weba` and `.flac` up to 100 MB. The backend infers the audio
format from the MIME type when the filename has no extension, rejects empty
files with a clear error, and streams uploads inline with HTTP range support so
the preview player can seek. All three upload controls use the same reliable
audio handling.

### Eye-catching thumbnails

The **🖼️ Eye-Catching Thumbnails** card generates a JPG thumbnail for every
rendered clip (enabled by default). Choose:

* **Format** — YouTube 16:9 (1280×720), Shorts/Reels 9:16 (1080×1920),
  square 1:1 (1080×1080), or match the clip's aspect ratio.
* **Style** — Viral Punch, Cinematic, Neon Glow, or Clean Minimal.

Thumbnails use a strong hook frame, cover crop, colour treatment, readable
gradient, optional virality badge and the clip title. They are bundled in the
batch ZIP and can be downloaded individually with the **🖼️ JPG** button next to
each finished clip.

### Video color grading

The **🎨 Video Color** card (right after *Your Facecam Avatar*) adds a color grade
to every rendered clip:

* **Brightness**, **Contrast**, **Saturation** (−100…+100), **Hue**
  (−180…+180°) and **Temperature** (−100 cool … +100 warm).
* One-click presets: Normal, Cinematic, Vivid, Warm, Cool, B&W, Faded.
* The grade is applied to the source video before titles/subtitles/watermarks are
  burned in, so text keeps its original color.

### Kecepatan & stabilitas (1.0.7)

* **Analisis lebih cepat:** terjemahan transkrip diproses per **800 baris** (dulu
  150) dan memakai model **Gemini Flash Lite** lebih dulu, sehingga jumlah
  request turun drastis dan antrean kuota harian tidak mudah habis.
* **Render lebih cepat:** encoder CPU memakai `libx264 ultrafast` dengan CRF 20,
  dan pemindaian wajah/facecam dipangkas dari 9 ke 5 sampel frame. Render
  hardware (NVENC/AMF/QuickSync) tetap diprioritaskan bila tersedia.
* **Error lebih jelas:** saat kuota Gemini habis, aplikasi langsung berhenti dan
  menampilkan pesan Bahasa Indonesia lengkap dengan perkiraan waktu reset,
  bukan retry berulang yang menghabiskan kuota model lain.

### Reliability & speed (1.0.6)

* **Performance rebuild (same 1.0.6):** the frozen backend dropped from about
  **1.34 GB to 589 MB**, the NSIS installer from **562 MB to 334 MB**, the
  portable EXE from **562 MB to 310 MB**, and the portable ZIP from
  **739 MB to 429 MB**. PyTorch is no longer shipped or imported, transcription
  uses a small whisper.cpp CLI, and FFmpeg uses the essentials build. First
  launch extracts far less data and the app starts noticeably faster.
* **Google Drive** analysis now returns the downloaded local video URL, so the
  preview and Server Engine render the same file instead of trying to re-open the
  Drive share link.
* **Upload Video File** now keeps the original video in the uploads folder.
  Before, only the browser-extracted audio was uploaded, which made server-side
  rendering fail because there was no video stream to slice.
* In the desktop app, selecting a local video uses a fast local import
  (`webUtils.getPathForFile` + a localhost-only endpoint) that hard-links or
  copies the file without sending multi-gigabyte data through HTTP. The browser
  version falls back to uploading the original video with live progress.
* Added a **Facebook / Threads** source tab. Public Facebook, Threads, Instagram,
  TikTok and X videos are downloaded locally, transcribed with Whisper AI, and
  analyzed with the same heatmap/clip flow. Threads uses a public-page metadata
  extractor because `yt-dlp` does not have a Threads extractor yet.
* Google Drive downloads are now validated as real video files (not HTML login
  or permission pages) before analysis starts.
* The desktop build now bundles a lightweight whisper.cpp CLI and quantized
  `base` model, so Drive, Facebook/Threads, and uploaded videos can be
  transcribed locally without shipping ~1 GB of PyTorch. The smaller FFmpeg
  essentials binaries (with libass subtitles + HW encoders) also cut the
  installer size and first-launch extraction time substantially.
* The render request now uses `result.video_url` first, fixing the old bug where
  Drive/upload renders fell back to an empty or YouTube URL.
* Incomplete or corrupt source segments are retried automatically once before a
  clip is marked as failed.
* Packaged FFmpeg receives an explicit `fontfile=` for every title/watermark
  `drawtext`, avoiding the fontconfig crash that used to abort renders.
* Face tracking samples fewer frames and is skipped for 16:9 landscape renders,
  where no horizontal crop is needed. Hardware encoders such as Intel QSV are
  used automatically and fall back to CPU only when necessary.
* **Clear Temp** is available in the packaged desktop app and preserves uploaded
  BGM, voice-over, hook SFX and fonts. Only disposable render cache is removed.
* AI analysis uses the newest Gemini Flash model discovered for your API key, so
  deprecated model names no longer cause an extra failed request.

### Render engines

* **Server Engine** (`auto`, `nvenc`, `amf`, `qsv`, `cpu`) supports every feature:
  color grading, pitch, facecam, voice over, BGM, SFX, watermark and captions.
* **Browser Engine** (`browser_wasm`) renders locally with FFmpeg WASM and
  supports aspect ratio, background style, color grading and original-voice
  pitch. Captions, facecam, voice over, BGM, SFX, thumbnails and watermark are
  not available there, so the app automatically falls back to the Server Engine
  when any of those features is enabled.

---

## 📱 Mobile App (Android APK + PWA)

SinyalAbidnet Kliper Pro has a native Android shell (WebView) that can be
installed on a phone, plus a PWA option for Android/iPhone. The mobile app is a
**client**: the backend (desktop app or `start-mobile.bat`) must be running on a
PC/VPS that the phone can reach over Wi-Fi or the internet.

### Files

| File | Location |
| --- | --- |
| Android APK | `mobile/release/SinyalAbidnet-Kliper-Pro-Mobile-1.0.3.apk` |
| APK inside the installer/portable/ZIP | next to `SinyalAbidnet Kliper Pro.exe` |
| LAN server launcher (source) | `start-mobile.bat` |
| LAN server launcher (installed app) | `start-mobile.bat` in the install folder |

### Option A — Desktop app (easiest)

1. Install/run **SinyalAbidnet Kliper Pro 1.0.7** on the PC.
2. Click the **📱 Mobile** button in the app header.
   * The backend restarts on `0.0.0.0` and the LAN URL is copied to the
     clipboard, e.g. `http://192.168.1.10:54321`.
   * Allow the Windows Firewall prompt for `cheat-clip-backend.exe` on
     **Private networks** if it appears.
3. Install the APK on the phone (see below) and enter that URL on first launch.
4. Click **📱 Mobile** again to turn LAN access off.

The installer and ZIP include the APK next to the executable, so you can copy it
to the phone via USB, WhatsApp, Google Drive, etc. The portable exe extracts the
APK alongside the app while it is running.

### Option B — Source checkout (`start-mobile.bat`)

```bat
start-mobile.bat
```

This builds `dist` if needed, sets `HOST=0.0.0.0`, `PORT=8000`, disables the
reloader, prints the LAN URL (e.g. `http://192.168.1.10:8000`) and starts the
backend. Allow port `8000` in Windows Firewall if prompted:

```powershell
# Run PowerShell as Administrator
netsh advfirewall firewall add rule name="SinyalAbidnet Kliper Pro" dir=in action=allow protocol=TCP localport=8000
```

### Option C — VPS / public server (PC can be turned off)

The APK can point to a VPS that runs the backend 24/7. See
`deploy/vps/README.md` for the full guide. In short:

1. Point a subdomain (for example `klip.sinyalrdm.id`) to the VPS IP.
2. Copy `.env.example` to `.env` and fill `GEMINI_API_KEY`.
3. Run `bash deploy/vps/deploy.sh` as root on Debian 11/12.
4. Enter `https://klip.sinyalrdm.id` in the APK's **Ganti Server** menu and use
   the generated access code on the login page.

The deploy script sets an optional `ACCESS_TOKEN` gate, binds the backend only
to `127.0.0.1`, puts Nginx + Let's Encrypt HTTPS in front, and raises the upload
limit to 4 GB. A minimal VPS is 2 vCPU / 4 GB RAM / 30 GB SSD; Debian 10 and
512 MB plans are not supported.

### Install the APK

1. Copy `SinyalAbidnet-Kliper-Pro-Mobile-1.0.3.apk` to the phone.
2. Open it and allow **Install unknown apps** for the file manager/browser.
3. Launch **SinyalAbidnet Kliper Pro**.
4. Enter the server URL shown by the **📱 Mobile** button or `start-mobile.bat`
   (for example `http://192.168.1.10:8000`) and tap **Simpan & Buka**.
   * The app tests `/api/health` before saving.
   * If the test fails, you can still choose **Simpan Tetap** (useful when the
     firewall rule is added afterwards).
5. Long-press the page or open **⋮ → Ganti Server** to change the server later.
   **⋮ → Muat Ulang** reloads and **⋮ → Buka di Browser** opens the URL in the
   phone browser.

The APK needs Android 7.0+ (API 24) and targets Android 15. Downloads are saved
to `Downloads/SinyalAbidnet Kliper Pro/` on Android 10+. On Android 7–9 the
system download manager uses the app's external files folder; grant storage
permission to save browser-rendered files to public Downloads.

### Option C — PWA (Android/iPhone, no APK)

Open `http://<PC-IP>:8000` in the phone browser:

* **Android Chrome:** ⋮ → **Install app** / **Add to Home screen**.
* **iPhone Safari:** Share → **Add to Home Screen**.

The app ships a web manifest, icons and a service worker. A **full** PWA
(offline shell/service worker) requires **HTTPS** or `localhost`; on a plain LAN
HTTP address the browser only creates a home-screen shortcut. Put the backend
behind HTTPS (Caddy, Nginx, Cloudflare Tunnel, etc.) if you want the full PWA.

### Build the APK from source

Requirements: JDK 17, Android SDK with `compileSdk 35` + `build-tools 35.x`,
and Gradle 8.9+ (the project is tested with Gradle 8.11.1 / AGP 8.7.3).

1. Create `mobile/android/local.properties`:

   ```properties
   sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk
   ```

2. Build:

   ```bat
   gradle -p mobile/android assembleRelease
   ```

   or open `mobile/android` in Android Studio and build the `release` variant.

3. Output: `mobile/android/app/build/outputs/apk/release/app-release.apk`.

The checked-in build is signed with the local **Android debug keystore** so it
can be sideloaded directly. For Google Play, replace `signingConfigs.release`
in `mobile/android/app/build.gradle` with your own upload keystore.

### Security note

LAN mode has **no authentication**. Only enable it on a trusted home/office
network. Do not expose port `8000` (or the desktop backend port) directly to the
public internet without a reverse proxy, HTTPS and access control.



