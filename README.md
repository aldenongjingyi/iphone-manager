# iPhone Manager

Transfer and delete photos/videos from your iPhone — no iTunes, no terminal, no setup. Works on macOS and Windows.

---

## Download

| Platform | File |
|----------|------|
| **macOS** | [iPhone.Manager-mac.dmg](https://github.com/aldenongjingyi/iphone-manager/releases/latest) |
| **Windows** | [iPhone.Manager-Setup-win.exe](https://github.com/aldenongjingyi/iphone-manager/releases/latest) |

> If the links show "not found", the first build is still running — check [Actions](https://github.com/aldenongjingyi/iphone-manager/actions) and try again in a few minutes.

---

## Install

### macOS

1. Download the `.dmg`
2. Open it and drag **iPhone Manager** into Applications
3. **First time only:** right-click the app → **Open** — this bypasses macOS's warning about apps not from the App Store. You only ever need to do this once.
4. Plug in your iPhone and tap **Trust** if it asks

### Windows

1. Download the `.exe` installer and run it
2. If **Windows SmartScreen** appears, click **More info → Run anyway** — this shows because the app isn't code-signed with a paid certificate
3. Launch **iPhone Manager** from the Start menu or desktop shortcut
4. Install [Apple Devices](https://apps.microsoft.com/detail/9NP83LWLPZ9K) from the Microsoft Store if you haven't already — this gives Windows the driver to talk to your iPhone over USB

---

## How it works

iPhone Manager is a desktop app that runs a small local server and opens it in a built-in browser window (powered by Electron). Your iPhone communicates over the USB cable — nothing leaves your machine, no account needed, fully offline.

---

## Usage

1. Open the app — it starts automatically when launched
2. Plug your iPhone in via USB
3. Tap **Trust** on the iPhone if the dialog appears
4. Wait a moment for your photos to load
5. Select files — individually or click **Select all**
6. Click **📁** to choose a destination folder (native OS dialog)
7. Click **Transfer**
8. Optionally enable **Delete after** — the app always asks for confirmation before removing anything from the iPhone

The app tracks every transferred file. Running it again will never copy the same file twice.

---

## Features

- Auto-detects iPhone plug/unplug — no restart needed
- Storage bar showing Photos & Videos, Other, and Free space
- Grid view with thumbnails or list view
- Filter by Photos, Videos, or Not yet transferred
- Real-time progress bar
- SQLite history — no duplicate transfers ever
- Native OS folder picker dialog
- Delete from iPhone only after explicit confirmation
- macOS and Windows

---

## Troubleshooting

**"iPhone Manager cannot be opened" (macOS)**
Right-click the app → Open → Open. One-time only.

**SmartScreen warning (Windows)**
Click More info → Run anyway. Appears because we don't pay for a code-signing certificate.

**iPhone not detected**
Make sure the iPhone is unlocked when you plug it in. Tap Trust when the dialog appears on the iPhone screen. The app checks every 3 seconds.

**Files don't appear**
Keep the iPhone unlocked while the app is reading it. Large libraries can take 10–30 seconds to load.

**Windows: iPhone not detected even after tapping Trust**
Open Apple Devices or iTunes once to complete the initial pairing, then relaunch the app.

**Transfer is slow**
Use a USB 3 port (marked SS or blue). USB 2 maxes out at ~25 MB/s, which is slow for HEIC or 4K video.

---

## Developer setup

To run from source (requires Python 3.10+ and Node.js 18+):

```bash
# macOS
brew install libimobiledevice
python3 -m pip install flask pymobiledevice3
npm install
npm start       # launches Electron + Python backend together
```

```bat
REM Windows — in Command Prompt
python -m pip install flask pymobiledevice3
npm install
npm start
```

To build the distributable yourself:

```bash
npm run build:mac   # → dist-electron/*.dmg
npm run build:win   # → dist-electron/*.exe  (run on Windows)
```

---

## Project structure

```
electron/
├── main.js         Electron main process — spawns Python, creates window
├── preload.js      Exposes electronAPI (folder picker) to the renderer
├── loading.html    Splash screen shown while Python backend starts
└── error.html      Shown if backend crashes mid-session

iphone_manager/
├── app.py          Flask backend — all routes, SSE events, entry point
├── device.py       iPhone detection, USB pairing, AFC file access
├── transfer.py     List files, copy to disk, delete from device
├── storage.py      Storage info from iPhone
├── database.py     SQLite transfer history
├── templates/index.html
└── static/style.css

main.py             PyInstaller entry point
package.json        npm — electron + electron-builder
electron-builder.yml  Build config (.dmg and NSIS .exe)
.github/workflows/build.yml  CI: builds both platforms, publishes release
```

Transfer history is stored at `~/.iphone_manager/transfer_history.db`.
