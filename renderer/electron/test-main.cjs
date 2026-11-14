// Exercise the actual main-process handlers with a fake Electron boundary.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const handlers = new Map();
const calls = [];
let window;
class BrowserWindow {
  constructor() {
    window = this;
    this.webContents = {
      mainFrame: { url: pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '?embed=1' },
      setWindowOpenHandler: (fn) => { this.openHandler = fn; },
      on: () => {}, session: { setPermissionRequestHandler: () => {} },
    };
  }
  setAlwaysOnTop() {} setVisibleOnAllWorkspaces() {} loadFile() {} on() {}
  isAlwaysOnTop() { return true; }
  getPosition() { return [100, 200]; }
  setPosition(...args) { calls.push(['position', ...args]); }
  setSize(...args) { calls.push(['size', ...args]); }
}
const electron = {
  BrowserWindow,
  app: { whenReady: () => ({ then: (fn) => fn() }), on: () => {}, quit: () => calls.push(['quit']) },
  ipcMain: { handle: (name, fn) => handlers.set(name, fn), on: (name, fn) => handlers.set(name, fn) },
  Menu: { buildFromTemplate: () => [] },
  Tray: class { setToolTip() {} on() {} setContextMenu() {} },
  nativeImage: { createFromPath: () => ({ isEmpty: () => false }) },
  screen: { getPrimaryDisplay: () => ({ workArea: { x: 0, y: 0, width: 1920, height: 1080 } }) },
  globalShortcut: { register: () => {}, unregisterAll: () => {} },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8'), {
  require: (name) => name === 'electron' ? electron : require(name), __dirname, process: { argv: [] },
});
const event = { sender: window.webContents, senderFrame: window.webContents.mainFrame };
const invoke = (name, ...args) => handlers.get(name)(event, ...args);
invoke('pet:resize', NaN);
invoke('pet:resize', -1);
invoke('pet:resize', 500);
handlers.get('pet:resize')({ sender: {}, senderFrame: event.senderFrame }, 2);
handlers.get('pet:quit')({ sender: event.sender, senderFrame: { url: event.senderFrame.url } });
assert.equal(calls.length, 0);
invoke('pet:resize', 2);
assert.deepEqual(calls.pop(), ['size', 384, 416, true]);
invoke('pet:drag-start', 10, 20);
invoke('pet:drag-move', Infinity, 30);
assert.equal(calls.length, 0);
invoke('pet:drag-move', 40, 50);
assert.deepEqual(calls.pop(), ['position', 130, 230]);
invoke('pet:drag-end');
invoke('pet:drag-move', 50, 50);
assert.equal(calls.length, 0);
assert.equal(window.openHandler().action, 'deny');
console.log('electron: IPC regression assertions passed');
