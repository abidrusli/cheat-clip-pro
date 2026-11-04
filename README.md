# 🎬 SinyalAbidnet Kliper Pro

> **AI Powered Auto Clipper — Turn long YouTube, Google Drive, and uploaded videos into viral TikToks, Shorts, and Reels with animated subtitles, face centering, and music in minutes.**

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

> **Note:** The desktop build excludes the Whisper/PyTorch auto-transcription
> model to keep the installer small. YouTube captions and manually supplied
> subtitles (`.srt` / `.txt`) still work fully.

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

### Portable build (no installation)

You can also produce a single portable executable and a zipped folder that run
without installing anything:

```bash
npm run desktop:portable
```

Outputs in `desktop/release/`:

* `SinyalAbidnet-Kliper-Pro-<version>-portable.exe` — single self-extracting portable exe.
* `SinyalAbidnet-Kliper-Pro-<version>-win-x64.zip` — unzip and run `SinyalAbidnet Kliper Pro.exe`.

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

### Video color grading

The **🎨 Video Color** card (right after *Your Facecam Avatar*) adds a color grade
to every rendered clip:

* **Brightness**, **Contrast**, **Saturation** (−100…+100), **Hue**
  (−180…+180°) and **Temperature** (−100 cool … +100 warm).
* One-click presets: Normal, Cinematic, Vivid, Warm, Cool, B&W, Faded.
* The grade is applied to the source video before titles/subtitles/watermarks are
  burned in, so text keeps its original color.

### Render engines

* **Server Engine** (`auto`, `nvenc`, `amf`, `qsv`, `cpu`) supports every feature:
  color grading, pitch, facecam, voice over, BGM, SFX, watermark and captions.
* **Browser Engine** (`browser_wasm`) renders locally with FFmpeg WASM and
  supports aspect ratio, background style, color grading and original-voice
  pitch. Captions, facecam, voice over, BGM, SFX and watermark are not available
  there, so the app automatically falls back to the Server Engine when any of
  those features is enabled.



