// Minimal, context-isolated bridge for the desktop shell.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('petAPI', {
  isElectron: true,
  dragStart: (x, y) => ipcRenderer.invoke('pet:drag-start', x, y),
  dragMove: (x, y) => ipcRenderer.send('pet:drag-move', x, y),
  dragEnd: () => ipcRenderer.send('pet:drag-end'),
  menu: () => ipcRenderer.send('pet:menu'),
  quit: () => ipcRenderer.send('pet:quit'),
  resize: (scale) => ipcRenderer.invoke('pet:resize', scale),
  onState: (cb) => {
    ipcRenderer.on('pet:state', (_event, state) => cb(state));
  },
  onExpression: (cb) => {
    ipcRenderer.on('pet:expression', (_event, id) => cb(id));
  },
  onClickThrough: (cb) => {
    ipcRenderer.on('pet:click-through', (_event, value) => cb(value));
  },
});
