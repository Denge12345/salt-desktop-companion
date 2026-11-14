# 安装与调试

## 1. 安装到 Codex 原生 v2

### Windows

```powershell
$petDir = Join-Path $env:USERPROFILE ".codex\pets\salt"
New-Item -ItemType Directory -Force -Path $petDir | Out-Null
Copy-Item .\pets\salt\pet.json        -Destination $petDir -Force
Copy-Item .\pets\salt\spritesheet.webp -Destination $petDir -Force
Get-ChildItem $petDir
```

期望结果：

```text
pet.json
spritesheet.webp
```

### macOS / Linux

```bash
mkdir -p ~/.codex/pets/salt
cp pets/salt/pet.json pets/salt/spritesheet.webp ~/.codex/pets/salt/
ls -lh ~/.codex/pets/salt/
```

### 刷新

1. 从**系统托盘**完整退出 Codex（只关窗口可能不结束后台进程）。
2. 重启 Codex。
3. **设置 → Pets** → 刷新列表 → 选择「莎露朵」。

### Windows + WSL 后端

如果文件已正确安装但列表里没有：

- 参考仓库记录过上游问题 [openai/codex#20730](https://github.com/openai/codex/issues/20730)，请结合当前客户端版本排查；
- 如考虑切换任务执行后端，先确认对现有 WSL 工作流的影响；这不是保证有效的通用修复；
- 不要改 `pet.json`、不要转 v1、不要重做图集；
- 集成终端可以继续用 WSL。

## 2. 本地校验

```powershell
python tools/validate_atlas.py pets/salt/spritesheet.webp --json-out build/validation.json
```

通过时会输出：

```text
PASS  spritesheet.webp  1536x2288  WEBP  1.00 MiB  (0 errors, 0 warnings)
```

手工检查：

```powershell
python -c "from PIL import Image; im=Image.open('pets/salt/spritesheet.webp'); print(im.size, im.mode, im.format)"
# (1536, 2288) RGBA WEBP
```

再打开 `build/contact-sheet.png`：每一行应只有前 N 格有内容，其余为透明（红色描边表示未被使用），第 9–10 行 16 格都有内容。

## 3. 浏览器预览

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

打开 <http://127.0.0.1:8765/renderer/>。

- 左侧棋盘格上显示角色；右侧切换 9 个状态与 16 向视线；
- 拖动角色 = 页面内拖动演示；单击 = 挥手；双击 = 点赞庆祝；
- 鼠标在角色周围移动 = 16 向视线；
- 键盘 `1`–`9` 切状态，`L` 开关视线，`D` 自动演示；
- 状态面板底部显示 `state / row / col / timing / source`，可直接确认图集行是否读对。

调试参数：

| 参数 | 作用 |
| --- | --- |
| `?state=review&frame=2` | 冻结到指定状态/帧 |
| `?look=4&frame=0` | 冻结到 90° 视线 |
| `?embed=1` | 隐藏面板，铺满窗口（Electron 用） |
| `?plain=1` | 纯色背景，方便看边缘 |
| `?debug=1` | 标题栏输出视口/画布尺寸 |

> 普通浏览器直接打开 `file://` 页面时，ES 模块本身也可能被拦截，内置清单无法解决这一问题。请使用本地 HTTP 服务。Electron 的本地文件加载是独立运行方式。

## 4. Electron 桌宠

```powershell
cd renderer
npm install
npm start
```

开发模式（自动开 DevTools）：

```powershell
npm start -- --dev
```

行为：

| 操作 | 效果 |
| --- | --- |
| 按住角色拖动 | 移动窗口（IPC `pet:drag-*`） |
| 单击 | 挥手 + 固定台词 |
| 双击 | 点赞庆祝 |
| 右键 | 托盘菜单（状态、穿透、置顶、重置、退出） |
| 托盘单击 | 显示/隐藏 |
| `Ctrl+Alt+P` | 鼠标穿透开关 |
| `Ctrl+Alt+S` | 挥手 |
| 托盘 → 重置位置 | 把窗口放回屏幕右下角 |

窗口参数在 [`renderer/electron/main.js`](../renderer/electron/main.js)：`transparent: true`、`frame: false`、`alwaysOnTop`、`skipTaskbar: true`、`hasShadow: false`。

常见问题：

- **黑底/不透明**：Windows 关闭「透明效果」或显卡驱动会破坏透明窗口；确认 `transparent: true`，不要给 `body`/`html` 加不透明背景（本仓库 Embed 模式已设为透明）。
- **点不到角色**：可能开了鼠标穿透，按 `Ctrl+Alt+P` 关闭。
- **位置跑到屏幕外**：托盘 → 重置位置。
- **托盘图标空白**：确认 `renderer/assets/tray.png` 存在（`build_atlas.py` 会生成）。

打包（可选）：安装 `electron-builder`，把 `pets/salt/` 一起放进 `extraResources`，并在 `main.js` 里用 `process.resourcesPath` 解析路径。当前骨架按「从仓库根目录运行」设计。

## 5. PySide6 备选

```powershell
pip install PySide6
python renderer/pyside6/pet_window.py
```

- 无边框、透明、置顶；
- 拖动移动窗口，单击挥手，双击点赞庆祝，右键状态菜单；
- 时间表与 Web 渲染器一致；
- 首次运行如报 `cannot load spritesheet`，检查 `pets/salt/` 是否完整。

## 6. 增加/替换状态

1. 把 PNG 放到 `build/frames/<state>/00.png …`（192×208，透明）。
2. 跑：

```powershell
python tools/build_atlas.py --frames-dir build/frames
python tools/validate_atlas.py pets/salt/spritesheet.webp
```

3. 若改了帧数/时序，同步更新 `pets/salt/pet.extended.json` 的 `frames` / `tracks`；官方 Codex 仍按固定 6/8/8/4/5/8/6/6/6 播放。
4. 重新安装（覆盖两个文件）并重启 Codex。

## 7. 卸载

```powershell
Remove-Item -Recurse -Force (Join-Path $env:USERPROFILE ".codex\pets\salt")
```

Electron/PySide6 关闭窗口即可；`renderer/node_modules` 可随时删除。

## 8. 性能

- 图集 1.00 MiB，单次解码 1536×2288 RGBA ≈ 14 MB 显存/内存，桌面宠物无压力。
- Web/Electron 用 `requestAnimationFrame` 推进时钟，仅在源帧坐标变化时重绘；相同状态文本不重复写入 DOM。CPU 占用需要实测。
- PySide6 用 33 ms 定时器、实际经过时间和源矩形绘制，避免逐帧 `QPixmap.copy`。
- 若自行替换成 16 MiB 图集，注意解码后的内存（1536×2288×4 ≈ 14 MB，与文件大小无关）。
