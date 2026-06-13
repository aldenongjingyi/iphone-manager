# iPhone Manager

Transfer and delete photos/videos from your iPhone — no iTunes required. Opens in your browser, works on macOS and Windows.

---

## How sharing works

This app runs **on your computer**, not in the cloud. That's because your iPhone connects over USB — a cloud server can't see your cable. The link you share is the install command below. The other person runs it once on their own machine, and the app opens in their browser automatically.

---

## Install

### macOS

```bash
brew install libimobiledevice
pip install git+https://github.com/aldenongjingyi/iphone-manager
iphone-manager
```

### Windows

1. Install **[Apple Devices](https://apps.microsoft.com/detail/9NP83LWLPZ9K)** from the Microsoft Store (or iTunes — either works).
2. Install **[Python 3.10+](https://www.python.org/downloads/)** — check "Add Python to PATH" during setup.
3. Open a terminal and run:

```bat
pip install git+https://github.com/aldenongjingyi/iphone-manager
iphone-manager
```

Browser opens at `http://localhost:5000`. Plug in your iPhone, tap **Trust** if prompted, and you're in.

---

## Usage

1. Run `iphone-manager`
2. Plug your iPhone into USB
3. Tap **Trust** on the iPhone if it asks
4. Wait a few seconds for your photos to load
5. Select files — individually or all at once
6. Choose a destination folder on your computer
7. Click **Transfer**
8. Optionally toggle **Delete after** to remove files from the iPhone once transferred — it always asks for confirmation first

The app remembers what you've already transferred, so running it again will never copy the same file twice.

---

## Features

- Detects plug/unplug automatically — no restart needed
- Storage bar showing Photos & Videos, Other, and Free space
- Grid view with thumbnails, or list view — your choice
- Filter by Photos, Videos, or Not yet transferred
- Real-time progress bar during transfer
- Transfer history log so duplicates are never copied again
- Delete from iPhone only after explicit confirmation — never automatic
- Works on macOS and Windows

---

## Alternative: clone and run

If you'd rather not use pip:

```bash
git clone https://github.com/aldenongjingyi/iphone-manager
cd iphone-manager
bash setup.sh
bash run.sh
```

`setup.sh` installs everything into a local `.venv`. On Windows use `setup.bat` and `run.bat`.

---

## Troubleshooting

**"Please tap Trust on your iPhone"**
Unlock your iPhone before plugging it in. The app retries every 3 seconds — just tap Trust on the iPhone when the dialog appears.

**Files don't appear**
Keep the iPhone unlocked while the app is reading it. Large photo libraries can take 10–30 seconds to index.

**Transfer is slow**
Plug into a USB 3 port (usually blue or marked SS). USB 2 caps out around 25 MB/s, which is slow for large HEIC or 4K video files.

**macOS: "ideviceinfo not found"**
```bash
brew install libimobiledevice
```

**Windows: iPhone not detected**
Open the Apple Devices app or iTunes at least once to complete the initial device pairing. Then relaunch `iphone-manager`.

**"pymobiledevice3 not installed"**
```bash
pip install pymobiledevice3
```

---

## Project structure

```
iphone_manager/
├── app.py          Flask backend — all routes, SSE events, entry point
├── device.py       iPhone detection, USB pairing, AFC file access
├── transfer.py     List files, copy to disk, delete from device
├── storage.py      Read storage info from iPhone
├── database.py     SQLite — tracks every transferred file
├── templates/
│   └── index.html  Single-page UI
└── static/
    └── style.css
pyproject.toml      pip package — defines the iphone-manager command
setup.sh            macOS setup without pip
setup.bat           Windows setup without pip
```

Transfer history is stored at `~/.iphone_manager/transfer_history.db`.
