import {
  CELL_H,
  CELL_W,
  STANDARD_STATES,
  PetPlayer,
  lookIndexForVector,
  normalizePet,
  resolveSpritesheet,
} from './pet-core.js';

const PET_DIR = new URL('../pets/salt/', import.meta.url);
const MANIFEST_URL = new URL('pet.json', PET_DIR).href;
const FALLBACK_MANIFEST = {
  id: 'salt',
  displayName: '莎露朵',
  description: '来自《舞萌DX》CAFE MiLK 的淡紫发猫娘面包师，正在寻找传说中的蓝色面粉。',
  spriteVersionNumber: 2,
  spritesheetPath: 'spritesheet.webp',
};

const EMBED = Boolean(window.petAPI) || new URLSearchParams(location.search).has('embed');
const PARAMS = new URLSearchParams(location.search);
const canvas = document.getElementById('pet');
const ctx = canvas.getContext('2d');
const stage = document.getElementById('stage');
const statusEl = document.getElementById('status');
const fpsEl = document.getElementById('fps');
const lookpad = document.getElementById('lookpad');
const statesEl = document.getElementById('states');
const lookReadout = document.getElementById('look-readout');

document.body.classList.toggle('embed', EMBED);
document.documentElement.classList.toggle('embed', EMBED);
canvas.width = CELL_W * 2;
canvas.height = CELL_H * 2;
ctx.imageSmoothingEnabled = false;

const state = {
  manifest: normalizePet(FALLBACK_MANIFEST),
  source: 'fallback',
  image: null,
  expressionImage: null,
  expressions: [],
  expression: null,
  scale: 2,
  lookEnabled: true,
  demo: false,
  freeze: false,
  dragging: false,
  pointerDown: false,
  moved: 0,
  downAt: 0,
  dragOffset: { x: 0, y: 0 },
  lastFrame: 0,
  fps: 0,
  errors: [],
};

let player = new PetPlayer(state.manifest, { state: 'idle' });
window.__salt = { state, player, get manifest() { return state.manifest; } };

function toast(text, ms = 1600) {
  const el = document.getElementById('toast');
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, ms);
}

async function boot() {
  let raw = null;
  try {
    const res = await fetch(MANIFEST_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    raw = await res.json();
    state.source = MANIFEST_URL;
  } catch (err) {
    state.source = 'fallback (file:// 或缺少 pet.json)';
    state.errors.push(String(err));
  }
  // Optional third-party extension: cell / columns / frames / tracks / sequences.
  // Codex itself only reads pet.json, but this renderer can honour the extras.
  if (raw) {
    try {
      const extRes = await fetch(new URL('pet.extended.json', PET_DIR), { cache: 'no-cache' });
      if (extRes.ok) {
        raw = { ...raw, ...(await extRes.json()) };
        state.source = `${MANIFEST_URL} + pet.extended.json`;
      }
    } catch {
      /* optional file */
    }
    state.manifest = normalizePet(raw);
  }
  player = new PetPlayer(state.manifest, { state: 'idle' });
  window.__salt.player = player;

  const sheetUrl = state.source.startsWith('http')
    ? resolveSpritesheet(state.manifest, MANIFEST_URL)
    : new URL(state.manifest.spritesheetPath, PET_DIR).href;

  const img = new Image();
  img.decoding = 'async';
  img.onload = () => {
    state.image = img;
    if (img.naturalWidth !== 1536 || img.naturalHeight !== 2288) {
      state.errors.push(`图集尺寸 ${img.naturalWidth}×${img.naturalHeight}，期望 1536×2288`);
    }
    buildUi();
    applyDebugParams();
    requestAnimationFrame(loop);
  };
  img.onerror = () => {
    state.errors.push(`无法加载图集: ${sheetUrl}`);
    buildUi();
    requestAnimationFrame(loop);
  };
  img.src = sheetUrl;

  buildStates();
  buildLookpad();
  bindControls();
  loadExpressions();
  if (PARAMS.has('debug')) {
    setInterval(() => {
      document.title = `DBG ${innerWidth}x${innerHeight} dpr${devicePixelRatio} stage ${stage.clientWidth}x${stage.clientHeight} canvas ${canvas.clientWidth}x${canvas.clientHeight} cs ${getComputedStyle(canvas).width} ${getComputedStyle(canvas).height} st ${getComputedStyle(stage).height}`;
    }, 100);
  }
  const name = state.manifest.displayName.replace(/\s+/g, ' ');
  document.getElementById('pet-name').textContent = name;
  document.getElementById('pet-version').textContent = `v${state.manifest.spriteVersionNumber}`;
  document.getElementById('atlas-size').textContent =
    `${state.manifest.cell.width * state.manifest.columns} × ${state.manifest.cell.height * state.manifest.rows}`;
}

function applyDebugParams() {
  const s = PARAMS.get('state');
  if (s && STANDARD_STATES.includes(s)) {
    playStandard(s, { restart: true });
    markActive();
  }
  const look = PARAMS.get('look');
  if (look != null && look !== '' && Number.isFinite(Number(look))) {
    player.setLook(Number(look));
    updateLookpad(Number(look));
    lookReadout.textContent = `${Number(look) * 22.5}°`;
  }
  const frame = Number(PARAMS.get('frame'));
  if (Number.isFinite(frame) && PARAMS.has('frame')) {
    player.index = Math.max(0, Math.min(player.frameCount - 1, Math.round(frame)));
    state.freeze = true;
  }
  if (PARAMS.get('freeze') === '1') state.freeze = true;
  if (PARAMS.get('plain') === '1') stage.classList.add('plain');
}

function buildUi() {
  if (EMBED) {
    document.getElementById('hint').style.display = 'none';
  }
}

function buildStates() {
  statesEl.innerHTML = '';
  for (const s of STANDARD_STATES) {
    const b = document.createElement('button');
    b.className = 'state';
    b.dataset.state = s;
    b.innerHTML = `<span>${labelFor(s)}</span><code>${state.manifest.frames[s]}f</code>`;
    b.title = `播放 ${s}`;
    b.addEventListener('click', () => {
      playStandard(s, { restart: true });
      markActive();
    });
    statesEl.appendChild(b);
  }
  markActive();
}

function labelFor(s) {
  return {
    idle: '待机',
    'running-right': '向右移动',
    'running-left': '向左移动',
    waving: '挥手',
    jumping: '点赞庆祝',
    failed: '摇头受挫',
    waiting: '等待确认',
    running: '工作中',
    review: '检查中',
  }[s] || s;
}

function markActive() {
  for (const b of document.getElementById('expressions').children) {
    b.classList.toggle('active', b.dataset.expression === state.expression?.id);
  }
  for (const b of statesEl.children) {
    b.classList.toggle('active', !state.expression && b.dataset.state === player.state);
  }
}

function playStandard(s) {
  if (!STANDARD_STATES.includes(s)) return;
  state.expression = null;
  player.play(s);
  markActive();
}

function playExpression(id) {
  const expression = state.expressions.find((item) => item.id === id);
  if (!expression || !state.expressionImage) return;
  player.play(expression.state);
  state.expression = expression;
  markActive();
}

function renderRect() {
  if (!state.expression) return player.currentRect();
  return { x: player.index * CELL_W, y: state.expression.row * CELL_H,
    width: CELL_W, height: CELL_H, row: state.expression.row, col: player.index };
}

async function loadExpressions() {
  try {
    const response = await fetch(new URL('expressions.json', PET_DIR), { cache: 'no-cache' });
    if (!response.ok) return; // Optional: native-only installs still work.
    const data = await response.json();
    if (data.columns !== 8 || data.cell?.width !== CELL_W || data.cell?.height !== CELL_H ||
        data.spritesheetPath !== 'expressions.webp' || !Array.isArray(data.items) ||
        data.items.length < 1 || data.items.length > 16) throw new Error('扩展表情清单无效');
    const ids = new Set();
    for (const item of data.items) {
      if (typeof item.id !== 'string' || ids.has(item.id) || typeof item.label !== 'string' ||
          !STANDARD_STATES.includes(item.state) || item.state === 'idle' ||
          item.frames !== player.pet.frames[item.state] || !Number.isInteger(item.row) ||
          item.row < 0 || item.row >= data.items.length) throw new Error('扩展表情轨道无效');
      ids.add(item.id);
    }
    const image = await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('扩展表情图集加载失败'));
      img.src = new URL(data.spritesheetPath, PET_DIR).href;
    });
    if (image.naturalWidth !== 8 * CELL_W || image.naturalHeight !== data.items.length * CELL_H) {
      throw new Error('扩展表情图集尺寸无效');
    }
    state.expressionImage = image;
    state.expressions = data.items;
    const container = document.getElementById('expressions');
    for (const item of data.items) {
      const button = document.createElement('button');
      button.className = 'state';
      button.dataset.expression = item.id;
      button.textContent = item.label;
      button.addEventListener('click', () => playExpression(item.id));
      container.appendChild(button);
    }
    document.getElementById('expressions-block').hidden = false;
    if (PARAMS.has('expression')) {
      playExpression(PARAMS.get('expression'));
      applyDebugParams();
    }
  } catch (error) {
    state.errors.push(String(error)); // A broken optional sheet never blocks the main pet.
  }
}

function buildLookpad() {
  lookpad.innerHTML = '';
  for (let i = 0; i < 16; i += 1) {
    const b = document.createElement('button');
    const deg = i * 22.5;
    b.textContent = `${Math.round(deg)}°`;
    b.title = `${deg}°（${i >= 8 ? '第10行' : '第9行'}第${(i % 8) + 1}格）`;
    b.dataset.look = String(i);
    b.addEventListener('click', () => {
      state.lookEnabled = true;
      player.setLook(i);
      updateLookpad(i);
      lookReadout.textContent = `${deg}° · row ${9 + Math.floor(i / 8)} col ${(i % 8) + 1}`;
    });
    lookpad.appendChild(b);
  }
}

function updateLookpad(index) {
  for (const b of lookpad.children) b.classList.toggle('active', Number(b.dataset.look) === index);
}

function bindControls() {
  document.getElementById('look-off').addEventListener('click', () => {
    state.lookEnabled = false;
    player.setLook(null);
    updateLookpad(-1);
    lookReadout.textContent = '—';
    toast('视线已关闭，使用 idle 正面帧');
  });
  document.getElementById('ping').addEventListener('click', () => {
    playStandard('waving');
    markActive();
  });
  document.getElementById('jump').addEventListener('click', () => {
    playStandard('jumping');
    markActive();
  });
  document.getElementById('demo').addEventListener('click', (e) => {
    state.demo = !state.demo;
    e.currentTarget.classList.toggle('on', state.demo);
    if (state.demo) runDemo();
    else clearTimeout(demoTimer);
  });
  const scale = document.getElementById('scale');
  scale.addEventListener('input', () => {
    state.scale = Number(scale.value);
    document.getElementById('scale-out').textContent = `${state.scale}×`;
    stage.style.width = `${CELL_W * state.scale}px`;
    stage.style.maxWidth = '100%';
    if (EMBED) window.petAPI?.resize(state.scale);
  });
  document.getElementById('theme').addEventListener('click', () => {
    stage.classList.toggle('plain');
  });
  window.addEventListener('keydown', (e) => {
    const n = Number(e.key);
    if (n >= 1 && n <= 9) {
      playStandard(STANDARD_STATES[n - 1], { restart: true });
      markActive();
    } else if (e.key.toLowerCase() === 'l') {
      state.lookEnabled = !state.lookEnabled;
      if (!state.lookEnabled) player.setLook(null);
    } else if (e.key.toLowerCase() === 'd') {
      document.getElementById('demo').click();
    }
  });

  // pointer interaction -----------------------------------------------------
  stage.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !e.isPrimary) return;
    stage.setPointerCapture(e.pointerId);
    state.pointerDown = true;
    state.moved = 0;
    state.downAt = performance.now();
    state.startX = e.screenX;
    state.startY = e.screenY;
    state.downClientX = e.clientX;
    state.downClientY = e.clientY;
    stage.classList.add('dragging');
    if (EMBED) window.petAPI?.dragStart(e.screenX, e.screenY);
  });
  stage.addEventListener('pointermove', (e) => {
    if (state.pointerDown) {
      state.moved = Math.max(
        state.moved,
        Math.hypot(e.screenX - state.startX, e.screenY - state.startY),
      );
      if (EMBED) window.petAPI?.dragMove(e.screenX, e.screenY);
      else {
        canvas.style.transform = `translate(${e.clientX - state.downClientX}px, ${e.clientY - state.downClientY}px)`;
      }
      if (state.moved > 4) state.dragging = true;
    }
    if (state.lookEnabled && !state.dragging) {
      const r = stage.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const idx = lookIndexForVector(e.clientX - cx, e.clientY - cy, 14);
      player.setLook(idx);
      updateLookpad(idx ?? -1);
      if (idx != null) {
        lookReadout.textContent = `${idx * 22.5}° · row ${9 + Math.floor(idx / 8)} col ${(idx % 8) + 1}`;
      }
    }
  });
  const endPointer = (e) => {
    if (!state.pointerDown) return;
    const wasClick = state.pointerDown && state.moved < 5 && performance.now() - state.downAt < 650;
    state.pointerDown = false;
    state.dragging = false;
    stage.classList.remove('dragging');
    canvas.style.transform = '';
    if (stage.hasPointerCapture(e.pointerId)) stage.releasePointerCapture(e.pointerId);
    if (EMBED) window.petAPI?.dragEnd();
    if (wasClick && e.type === 'pointerup') {
      playStandard('waving');
      markActive();
      toast('「……のです。」');
    }
  };
  stage.addEventListener('pointerup', endPointer);
  stage.addEventListener('pointercancel', endPointer);
  stage.addEventListener('lostpointercapture', endPointer);
  stage.addEventListener('pointerleave', () => {
    if (state.lookEnabled && !state.pointerDown) {
      player.setLook(null);
      updateLookpad(-1);
      lookReadout.textContent = '—';
    }
  });
  stage.addEventListener('dblclick', () => {
    playStandard('jumping');
    markActive();
  });
  stage.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    if (EMBED) window.petAPI?.menu();
  });

  player.onStateChange = (s) => {
    if (state.expression && s !== state.expression.state) state.expression = null;
    markActive();
  };

  if (window.petAPI?.onState) {
    window.petAPI.onExpression?.(playExpression);
    window.petAPI.onState((s) => {
      playStandard(s);
      markActive();
    });
    window.petAPI.onClickThrough?.((enabled) => {
      stage.style.pointerEvents = enabled ? 'none' : '';
      toast(enabled ? '鼠标穿透已开启 · Ctrl+Alt+P 关闭' : '鼠标穿透已关闭');
    });
  }
}

let demoTimer = 0;
const DEMO_STATES = ['waving', 'review', 'waiting', 'running', 'failed', 'jumping', 'running-right', 'idle'];
function runDemo() {
  const next = DEMO_STATES[Math.floor(Math.random() * DEMO_STATES.length)];
  playStandard(next);
  markActive();
  demoTimer = setTimeout(() => {
    if (!state.demo) return;
    if (!player.track.loop) playStandard('idle');
    runDemo();
  }, 1800);
}

let last = performance.now();
let fpsAccum = 0;
let fpsFrames = 0;
let lastDrawKey = '';
let lastStatus = '';

document.addEventListener('visibilitychange', () => { last = performance.now(); });

function loop(now) {
  const dt = Math.min(80, now - last);
  last = now;
  if (!state.freeze) player.update(dt);
  draw();
  updateStatus();
  fpsAccum += dt;
  fpsFrames += 1;
  if (fpsAccum > 500) {
    state.fps = Math.round((fpsFrames * 1000) / fpsAccum);
    fpsAccum = 0;
    fpsFrames = 0;
    fpsEl.textContent = `${state.fps} fps`;
  }
  requestAnimationFrame(loop);
}

function draw() {
  const rect = renderRect();
  const source = state.expression ? state.expressionImage : state.image;
  const key = `${Boolean(source)}:${state.expression?.id || 'standard'}:${rect.x}:${rect.y}`;
  if (key === lastDrawKey) return;
  lastDrawKey = key;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!source) {
    ctx.fillStyle = 'rgba(120, 105, 150, 0.7)';
    ctx.font = '12px "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('spritesheet.webp 未加载', canvas.width / 2, canvas.height / 2 - 8);
    ctx.fillText('请用本地服务器打开，或检查 pets/salt/', canvas.width / 2, canvas.height / 2 + 12);
    return;
  }
  ctx.drawImage(
    source,
    rect.x, rect.y, rect.width, rect.height,
    0, 0, canvas.width, canvas.height,
  );
}

function updateStatus() {
  if (EMBED) return;
  const snap = player.snapshot();
  const rect = renderRect();
  const lines = [
    `state  ${state.expression?.label || snap.state}  ${snap.index + 1}/${snap.count}`,
    `atlas  row ${rect.row}  col ${rect.col}  ${rect.width}×${rect.height}`,
    `look   ${player.lookIndex == null ? 'front' : `${player.lookIndex * 22.5}° (${player.lookIndex})`}`,
    `timing ${snap.durations.join(' / ')} ms  ${snap.loop ? 'loop' : 'once'}`,
    `source ${state.source}`,
    state.errors.length ? `warn   ${state.errors[state.errors.length - 1]}` : 'ready  ✓',
  ];
  const text = lines.join('\n');
  if (text !== lastStatus) statusEl.textContent = text;
  lastStatus = text;
}

boot();
