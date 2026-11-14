/**
 * Framework-free Codex v2 pet player.
 *
 * Pure logic (no DOM) so the same module runs in the browser, in Electron and
 * under Node for tests.
 */

export const CELL_W = 192;
export const CELL_H = 208;
export const COLUMNS = 8;
export const ROWS = 11;
export const ATLAS_W = CELL_W * COLUMNS;
export const ATLAS_H = CELL_H * ROWS;

/** Codex v2 standard rows, in atlas order. */
export const STANDARD_STATES = [
  'idle',
  'running-right',
  'running-left',
  'waving',
  'jumping',
  'failed',
  'waiting',
  'running',
  'review',
];

/** Frames actually used per row (Codex / PetPack defaults). */
export const DEFAULT_FRAMES = [6, 8, 8, 4, 5, 8, 6, 6, 6];

/** Per-frame duration in ms; index matches STANDARD_STATES. */
export const DEFAULT_DURATIONS = [
  [200, 200, 200, 200, 200, 200],
  Array(8).fill(100),
  Array(8).fill(100),
  [180, 150, 150, 180],
  [140, 110, 150, 130, 180],
  Array(8).fill(170),
  Array(6).fill(220),
  Array(6).fill(150),
  Array(6).fill(180),
];

export const DEFAULT_LOOP = {
  idle: true,
  'running-right': true,
  'running-left': true,
  waving: false,
  jumping: false,
  failed: false,
  waiting: true,
  running: true,
  review: true,
};

const FALLBACK = {
  waving: 'idle',
  jumping: 'idle',
  failed: 'idle',
};

/** Fill defaults and normalise optional third-party manifest extensions. */
export function normalizePet(raw = {}) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) raw = {};
  const pet = {
    id: raw.id || 'salt',
    displayName: raw.displayName || raw.name || '莎露朵',
    description: raw.description || '',
    spriteVersionNumber: Number(raw.spriteVersionNumber || 1),
    spritesheetPath: raw.spritesheetPath || 'spritesheet.webp',
    cell: {
      width: positiveInt(raw.cell?.width ?? raw.cell?.[0], CELL_W),
      height: positiveInt(raw.cell?.height ?? raw.cell?.[1], CELL_H),
    },
    columns: positiveInt(raw.columns, COLUMNS),
    frames: { ...Object.fromEntries(STANDARD_STATES.map((s, i) => [s, DEFAULT_FRAMES[i]])), ...(raw.frames || {}) },
    tracks: {},
  };
  pet.rows = pet.spriteVersionNumber >= 2 ? 11 : 9;
  pet.regions = {
    standard: { x: 0, y: 0, width: pet.columns * pet.cell.width, height: 9 * pet.cell.height },
    look: pet.rows >= 11 ? { x: 0, y: 9 * pet.cell.height, width: 8 * pet.cell.width, height: 2 * pet.cell.height } : null,
  };

  for (const state of STANDARD_STATES) {
    const i = STANDARD_STATES.indexOf(state);
    const ext = raw.tracks?.[state] || {};
    const count = clampInt(pet.frames[state], 1, 8);
    pet.frames[state] = count;
    pet.tracks[state] = {
      durations: normalizeDurations(ext.durations, count, DEFAULT_DURATIONS[i]),
      loop: typeof ext.loop === 'boolean' ? ext.loop : DEFAULT_LOOP[state],
      fallback: STANDARD_STATES.includes(ext.fallback) ? ext.fallback : FALLBACK[state] || 'idle',
    };
  }
  pet.sequences = raw.sequences || {
    start: ['waving', 'idle'],
    done: ['jumping', 'waving', 'idle'],
    error: ['failed', 'idle'],
    approval: ['waiting'],
    working: ['running'],
    review: ['review'],
  };
  return pet;
}

function clampInt(v, lo, hi) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : lo;
}

function positiveInt(value, fallback) {
  const n = Number(value);
  return Number.isSafeInteger(n) && n > 0 ? n : fallback;
}

function normalizeDurations(durations, count, fallback) {
  const src = Array.isArray(durations) && durations.length ? durations.map(Number).filter((n) => Number.isFinite(n) && n > 0) : fallback;
  const out = [];
  for (let i = 0; i < count; i += 1) out.push(src[i % src.length] || 150);
  return out;
}

/** Rect of one standard frame in atlas pixels. */
export function cellRect(state, frameIndex, pet) {
  const row = STANDARD_STATES.indexOf(state);
  if (row < 0) throw new Error(`unknown state: ${state}`);
  const { width, height } = pet.cell;
  const col = frameIndex % pet.columns;
  return { x: col * width, y: row * height, width, height, row, col };
}

/** Rect of one of the 16 clockwise look frames (000 = up). */
export function lookRect(lookIndex, pet) {
  const i = ((Math.round(lookIndex) % 16) + 16) % 16;
  const { width, height } = pet.cell;
  return {
    x: (i % 8) * width,
    y: (9 + Math.floor(i / 8)) * height,
    width,
    height,
    row: 9 + Math.floor(i / 8),
    col: i % 8,
    angle: i * 22.5,
  };
}

/**
 * Map a screen-space vector (x right, y down) to a look frame.
 * Zero vector or inside the deadzone returns null (front / no gaze).
 */
export function lookIndexForVector(dx, dy, deadzone = 10) {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null;
  if ((dx === 0 && dy === 0) || Math.hypot(dx, dy) < deadzone) return null;
  const angle = (Math.atan2(dx, -dy) * 180) / Math.PI;
  const norm = (angle + 360) % 360;
  return Math.round(norm / 22.5) % 16;
}

export class PetPlayer {
  constructor(pet, { state = 'idle', autoFallback = true } = {}) {
    this.pet = normalizePet(pet);
    this.autoFallback = autoFallback;
    this.state = STANDARD_STATES.includes(state) ? state : 'idle';
    this.index = 0;
    this.elapsed = 0;
    this.lookIndex = null;
    this.oneShotCount = 0;
    this.onStateChange = null;
  }

  get track() {
    return this.pet.tracks[this.state];
  }

  get frameCount() {
    return this.pet.frames[this.state];
  }

  setState(state, { restart = false } = {}) {
    if (!STANDARD_STATES.includes(state)) return;
    if (state === this.state && !restart) return;
    this.state = state;
    this.index = 0;
    this.elapsed = 0;
    if (this.onStateChange) this.onStateChange(state);
  }

  /** Restart a state; non-looping tracks fall back after their last frame. */
  play(state) {
    this.setState(state, { restart: true });
    this.oneShotCount += 1;
  }

  setLook(index) {
    this.lookIndex = index == null || !Number.isFinite(index) ? null : ((Math.round(index) % 16) + 16) % 16;
  }

  setLookFromPoint(dx, dy, deadzone = 10) {
    this.lookIndex = lookIndexForVector(dx, dy, deadzone);
  }

  update(dtMs) {
    if (!Number.isFinite(dtMs) || dtMs <= 0) return;
    this.elapsed += dtMs;
    const durations = this.track.durations;
    // Skip complete cycles to keep long pauses bounded without a frame backlog.
    if (this.track.loop) this.elapsed %= durations.reduce((sum, n) => sum + n, 0);
    let guard = 0;
    while (this.elapsed >= durations[this.index] && guard < 64) {
      this.elapsed -= durations[this.index];
      this.index += 1;
      guard += 1;
      if (this.index >= this.frameCount) {
        if (this.track.loop) {
          this.index = 0;
        } else if (this.autoFallback) {
          this.state = this.track.fallback;
          this.index = 0;
          this.elapsed = 0;
          if (this.onStateChange) this.onStateChange(this.state);
          return;
        } else {
          this.index = this.frameCount - 1;
          this.elapsed = 0;
          return;
        }
      }
    }
  }

  /** Current atlas rect: gaze frame when idle+look, otherwise the state frame. */
  currentRect() {
    if (this.lookIndex != null && this.state === 'idle' && this.pet.spriteVersionNumber >= 2) {
      return lookRect(this.lookIndex, this.pet);
    }
    return cellRect(this.state, this.index, this.pet);
  }

  snapshot() {
    return {
      state: this.state,
      index: this.index,
      count: this.frameCount,
      look: this.lookIndex,
      durations: this.track.durations,
      loop: this.track.loop,
    };
  }
}

/** Resolve spritesheet URL relative to the manifest URL. */
export function resolveSpritesheet(pet, manifestUrl) {
  const base = manifestUrl || globalThis.location?.href || 'http://localhost/';
  return new URL(pet.spritesheetPath, base).href;
}
