'use strict';

const { app, BrowserWindow, dialog, ipcMain, shell, nativeTheme } = require('electron');
const { spawn } = require('child_process');
const path   = require('path');
const http   = require('http');
const net    = require('net');
const fs     = require('fs');

// ── globals ───────────────────────────────────────────────────────────────────

let mainWindow    = null;
let pythonProcess = null;
let serverPort    = null;
const isDev = !app.isPackaged;

// ── helpers ───────────────────────────────────────────────────────────────────

function getFreePort () {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function getPythonBinary () {
  if (isDev) {
    // Development: run main.py directly
    const interpreter = process.platform === 'win32' ? 'python' : 'python3';
    return { bin: interpreter, args: [path.join(__dirname, '..', 'main.py')] };
  }
  // Packaged: bundled binary in app's Resources folder
  const name = process.platform === 'win32' ? 'python-backend.exe' : 'python-backend';
  const bin  = path.join(process.resourcesPath, name);
  if (!fs.existsSync(bin)) {
    throw new Error(`Python backend not found at: ${bin}`);
  }
  return { bin, args: [] };
}

async function waitForBackend (port, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      if (Date.now() > deadline) {
        return reject(new Error('Python backend did not start within 20 s.'));
      }
      const req = http.get(`http://127.0.0.1:${port}/api/device`, (res) => {
        if (res.statusCode === 200) return resolve();
        setTimeout(attempt, 250);
      });
      req.on('error', () => setTimeout(attempt, 250));
      req.setTimeout(200, () => { req.destroy(); setTimeout(attempt, 250); });
    };
    attempt();
  });
}

function startPythonBackend (port) {
  const { bin, args } = getPythonBinary();
  const env = { ...process.env, PORT: String(port) };

  pythonProcess = spawn(bin, args, { env, windowsHide: true });

  pythonProcess.stdout.on('data', d => process.stdout.write(`[py] ${d}`));
  pythonProcess.stderr.on('data', d => process.stderr.write(`[py] ${d}`));

  pythonProcess.on('error', (err) => {
    console.error('Python process error:', err);
  });

  pythonProcess.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`Python exited with code ${code}`);
    }
  });
}

// ── window ────────────────────────────────────────────────────────────────────

function createLoadingWindow () {
  const win = new BrowserWindow({
    width: 420,
    height: 300,
    resizable: false,
    frame: false,
    transparent: true,
    show: false,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });
  win.loadFile(path.join(__dirname, 'loading.html'));
  win.once('ready-to-show', () => win.show());
  return win;
}

function createMainWindow (port) {
  const win = new BrowserWindow({
    width: 1240,
    height: 800,
    minWidth: 860,
    minHeight: 600,
    title: 'iPhone Manager',
    backgroundColor: '#0f0f12',
    show: false,
    // macOS: hide titlebar, keep traffic lights
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // Allow loading localhost
      webSecurity: true,
    },
  });

  win.loadURL(`http://127.0.0.1:${port}`);

  win.once('ready-to-show', () => {
    win.show();
    if (isDev) win.webContents.openDevTools({ mode: 'detach' });
  });

  // If Flask crashes mid-session, show a friendly error instead of blank page
  win.webContents.on('did-fail-load', (_e, code, desc) => {
    if (code === -102 /* ERR_CONNECTION_REFUSED */) {
      win.webContents.loadFile(path.join(__dirname, 'error.html'));
    }
  });

  win.on('closed', () => { mainWindow = null; });
  return win;
}

// ── app lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  nativeTheme.themeSource = 'dark';

  const loadingWin = createLoadingWindow();

  try {
    serverPort = await getFreePort();
    startPythonBackend(serverPort);
    await waitForBackend(serverPort);

    mainWindow = createMainWindow(serverPort);
    loadingWin.close();
  } catch (err) {
    loadingWin.close();
    await dialog.showErrorBox(
      'Failed to start iPhone Manager',
      `${err.message}\n\nTry relaunching the app. If the problem persists, reinstall it.`,
    );
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', async () => {
  if (!mainWindow && serverPort) {
    mainWindow = createMainWindow(serverPort);
  }
});

app.on('before-quit', () => {
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill();
  }
});

// ── IPC handlers ──────────────────────────────────────────────────────────────

// Native folder picker — called from renderer via window.electronAPI.pickFolder()
ipcMain.handle('pick-folder', async () => {
  // Don't attach as a sheet (no parent window arg) — sheets can silently
  // fail on macOS when titleBarStyle is 'hiddenInset'. Standalone dialog
  // works reliably on both platforms.
  if (mainWindow) mainWindow.focus();
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory', 'createDirectory'],
    title: 'Choose destination folder',
    buttonLabel: 'Select Folder',
  });
  return result.canceled ? null : result.filePaths[0];
});

// Open a path in Finder / Explorer
ipcMain.handle('show-in-folder', async (_e, filePath) => {
  shell.showItemInFolder(filePath);
});
