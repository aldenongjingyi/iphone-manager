# iPhone Manager

Transfer and delete photos/videos from your iPhone — no iTunes required. Opens in your browser, works on macOS and Windows.

---

## Download

| Platform | Download |
|----------|----------|
| **macOS** | [iphone-manager-mac.zip](https://github.com/aldenongjingyi/iphone-manager/releases/latest/download/iphone-manager-mac.zip) |
| **Windows** | [iphone-manager.exe](https://github.com/aldenongjingyi/iphone-manager/releases/latest/download/iphone-manager.exe) |

> Builds are created automatically. If the links show "not found", the first build is still running — check the [Actions tab](https://github.com/aldenongjingyi/iphone-manager/actions).

---

## Setup

### macOS

1. Download `iphone-manager-mac.zip` and unzip it
2. **First time only:** right-click the file → **Open** → Open (this bypasses macOS security for apps not from the App Store)
3. A terminal window opens and your browser goes to `http://localhost:5000`
4. Plug in your iPhone — tap **Trust** if it asks

After the first launch you can just double-click normally.

### Windows

1. Download `iphone-manager.exe` and double-click it
2. If Windows SmartScreen appears: click **More info** → **Run anyway**
3. Your browser opens to `http://localhost:5000`
4. Plug in your iPhone — tap **Trust** if it asks

> **Requirement:** [Apple Devices](https://apps.microsoft.com/detail/9NP83LWLPZ9K) (Microsoft Store) or iTunes must be installed for Windows to recognise the iPhone over USB.

---

## How it works

The app runs a small local server on your computer and opens it in your browser. Your iPhone communicates over the USB cable — no cloud, no account, nothing leaves your machine.

To stop it: close the terminal window (macOS) or the command prompt window (Windows).

---

## Usage

1. Open the app and plug in your iPhone
2. Tap **Trust** if the iPhone asks
3. Wait a moment for your photos to load
4. Select files — individually or use **Select all**
5. Type or paste a destination folder path (e.g. `~/Pictures/iPhone`)
6. Click **Transfer**
7. Optionally toggle **Delete after** — the app will ask you to confirm before removing anything from the iPhone

The app tracks every file it has transferred. Running it again will never copy the same file twice.

---

## Features

- Auto-detects plug/unplug — no restart needed
- Storage bar showing Photos & Videos, Other, and Free space
- Grid view with thumbnails, or list view
- Filter by Photos, Videos, or Not yet transferred
- Real-time progress bar
- SQLite history — no duplicate transfers
- Delete requires explicit confirmation, never automatic
- macOS and Windows

---

## Troubleshooting

**"iphone-manager cannot be opened" (macOS)**
Right-click the file → Open → Open. You only need to do this once.

**SmartScreen warning (Windows)**
Click More info → Run anyway. This appears because the app isn't signed with a paid certificate.

**iPhone not detected**
Make sure the iPhone is unlocked when you plug it in, and tap Trust when the dialog appears on the iPhone screen.

**Files don't appear**
Keep the iPhone unlocked while the app is reading it. Large photo libraries can take 10–30 seconds to index.

**Windows: iPhone not detected even after tapping Trust**
Open Apple Devices or iTunes once to complete the initial pairing. Then relaunch the app.

**Transfer is slow**
Use a USB 3 port (usually blue, or marked SS). USB 2 maxes out at around 25 MB/s.

---

## Developer setup

If you want to run from source instead of the binary:

```bash
# macOS
brew install libimobiledevice
python3 -m pip install git+https://github.com/aldenongjingyi/iphone-manager
python3 -m iphone_manager

# Windows
python -m pip install git+https://github.com/aldenongjingyi/iphone-manager
python -m iphone_manager
```

Or clone and run:

```bash
git clone https://github.com/aldenongjingyi/iphone-manager
cd iphone-manager
bash setup.sh && bash run.sh   # macOS
# setup.bat and run.bat on Windows
```
