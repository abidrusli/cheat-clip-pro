const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  getMobileStatus: () => ipcRenderer.invoke('mobile:get-status'),
  enableMobile: () => ipcRenderer.invoke('mobile:enable'),
  disableMobile: () => ipcRenderer.invoke('mobile:disable'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
});
