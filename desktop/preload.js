const electron = require('electron');
const { contextBridge, ipcRenderer } = electron;
const webUtils = electron.webUtils;

contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  getMobileStatus: () => ipcRenderer.invoke('mobile:get-status'),
  enableMobile: () => ipcRenderer.invoke('mobile:enable'),
  disableMobile: () => ipcRenderer.invoke('mobile:disable'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  // Electron 32+ gives the renderer a safe way to resolve a File selected via
  // <input type="file"> to its real path. The local backend can then hard-link
  // it instead of uploading a multi-gigabyte video over HTTP.
  getPathForFile: (file) => {
    try {
      return webUtils?.getPathForFile(file) || '';
    } catch {
      return '';
    }
  },
});
