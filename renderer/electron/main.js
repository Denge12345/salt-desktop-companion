// Electron shell for the Salt desktop pet.
// The renderer is the same framework-free page used by the browser preview;
// this file only adds a transparent, frameless, always-on-top window, window
// dragging, a tray menu and click-through.

const { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage, screen, globalShortcut } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const PAGE_URL = pathToFileURL(path.join(__dirname, '..', 'index.html')).href;

let win = null;
let tray = null;
let clickThrough = false;
let drag = null;

function trusted(event) {
  return Boolean(win && event.sender === win.webContents &&
    event.senderFrame === win.webContents.mainFrame &&
    event.senderFrame?.url.split('?')[0] === PAGE_URL);
}

function coordinates(x, y) {
  return Number.isFinite(x) && Number.isFinite(y) && Math.abs(x) < 1e6 && Math.abs(y) < 1e6;
}

const PET_STATES = [
  ['idle', '待机'],
  ['running-right', '向右移动'],
  ['running-left', '向左移动'],
  ['waving', '挥手'],
  ['jumping', '点赞庆祝'],
  ['failed', '摇头受挫'],
  ['waiting', '等待确认'],
  ['running', '工作中'],
  ['review', '检查中'],
];

function createWindow() {
  const { workArea } = screen.getPrimaryDisplay();
  const width = 400;
  const height = 434;
  win = new BrowserWindow({
    width,
    height,
    x: workArea.x + workArea.width - width - 28,
    y: workArea.y + workArea.height - height - 40,
    transparent: true,
    frame: false,
    resizable: true,
    hasShadow: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    fullscreenable: false,
    maximizable: false,
    title: '莎露朵',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.setAlwaysOnTop(true, 'floating');
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (event) => event.preventDefault());
  win.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.loadFile(path.join(__dirname, '..', 'index.html'), { query: { embed: '1' } });

  if (process.argv.includes('--dev')) {
    win.webContents.openDevTools({ mode: 'detach' });
  }

  win.on('blur', () => { drag = null; });
  win.on('closed', () => { drag = null; win = null; });
}

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

function toggleClickThrough(force) {
  clickThrough = typeof force === 'boolean' ? force : !clickThrough;
  drag = null;
  if (!win) return clickThrough;
  win.setIgnoreMouseEvents(clickThrough, { forward: true });
  refreshTray();
  send('pet:click-through', clickThrough);
  return clickThrough;
}

function refreshTray() {
  if (!tray) return;
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '莎露朵 · Salt', enabled: false },
    { type: 'separator' },
    ...PET_STATES.map(([id, label]) => ({
      label,
      click: () => send('pet:state', id),
    })),
    { label: '互动表情', submenu: [
      ['cheer', '比耶'], ['shy', '害羞'], ['excited', '期待'], ['cry', '哭泣'],
    ].map(([id, label]) => ({ label, click: () => send('pet:expression', id) })) },
    { type: 'separator' },
    {
      label: '鼠标穿透（Ctrl+Alt+P）',
      type: 'checkbox',
      checked: clickThrough,
      click: () => toggleClickThrough(),
    },
    {
      label: '窗口置顶',
      type: 'checkbox',
      checked: win ? win.isAlwaysOnTop() : true,
      click: (item) => win && win.setAlwaysOnTop(item.checked, 'floating'),
    },
    { label: '重置位置', click: resetPosition },
    { type: 'separator' },
    { label: '退出', role: 'quit' },
  ]));
}

function resetPosition() {
  if (!win) return;
  const { workArea } = screen.getPrimaryDisplay();
  const [w, h] = win.getSize();
  win.setPosition(workArea.x + workArea.width - w - 28, workArea.y + workArea.height - h - 40);
}

function createTray() {
  const iconPath = path.join(__dirname, '..', 'assets', 'tray.png');
  let icon = nativeImage.createFromPath(iconPath);
  if (icon.isEmpty()) icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip('莎露朵 · Codex v2 桌宠');
  tray.on('click', () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.show();
  });
  refreshTray();
}

app.whenReady().then(() => {
  createWindow();
  createTray();

  globalShortcut.register('CommandOrControl+Alt+P', () => toggleClickThrough());
  globalShortcut.register('CommandOrControl+Alt+S', () => send('pet:state', 'waving'));

  ipcMain.handle('pet:drag-start', (event, screenX, screenY) => {
    if (!trusted(event) || !coordinates(screenX, screenY)) return;
    const [x, y] = win.getPosition();
    drag = { startX: x, startY: y, cursorX: screenX, cursorY: screenY };
  });

  ipcMain.on('pet:drag-move', (event, screenX, screenY) => {
    if (!trusted(event) || !drag || !coordinates(screenX, screenY)) return;
    const dx = Math.round(screenX - drag.cursorX);
    const dy = Math.round(screenY - drag.cursorY);
    win.setPosition(drag.startX + dx, drag.startY + dy);
  });

  ipcMain.on('pet:drag-end', (event) => { if (trusted(event)) drag = null; });

  ipcMain.on('pet:menu', (event) => {
    if (trusted(event) && tray) tray.popUpContextMenu();
  });

  ipcMain.on('pet:quit', (event) => { if (trusted(event)) app.quit(); });

  ipcMain.handle('pet:resize', (event, scale) => {
    if (!trusted(event) || !Number.isFinite(scale) || scale < 1 || scale > 3) return;
    const w = Math.round(192 * scale);
    const h = Math.round(208 * scale);
    win.setSize(w, h, true);
  });
});

app.on('window-all-closed', () => app.quit());
app.on('will-quit', () => globalShortcut.unregisterAll());
