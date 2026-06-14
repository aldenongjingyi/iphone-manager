'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Signals to the renderer that it's running inside Electron
  isElectron: true,

  // Opens native OS folder picker, returns chosen path or null
  pickFolder: () => ipcRenderer.invoke('pick-folder'),

  // Reveal a file in Finder / Explorer
  showInFolder: (filePath) => ipcRenderer.invoke('show-in-folder', filePath),

  // Window controls (Windows custom titlebar)
  minimize:    () => ipcRenderer.invoke('minimize-window'),
  maximize:    () => ipcRenderer.invoke('maximize-window'),
  closeWindow: () => ipcRenderer.invoke('close-window'),
});
