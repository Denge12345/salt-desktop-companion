import assert from 'node:assert/strict';
import {
  DEFAULT_FRAMES,
  PetPlayer,
  cellRect,
  lookIndexForVector,
  lookRect,
  normalizePet,
} from './pet-core.js';

const pet = normalizePet({
  id: 'salt',
  displayName: '莎露朵',
  spriteVersionNumber: 2,
  spritesheetPath: 'spritesheet.webp',
});

assert.equal(pet.spriteVersionNumber, 2);
assert.equal(pet.rows, 11);
assert.deepEqual(pet.cell, { width: 192, height: 208 });
assert.deepEqual(pet.frames, Object.fromEntries(
  ['idle', 'running-right', 'running-left', 'waving', 'jumping', 'failed', 'waiting', 'running', 'review']
    .map((s, i) => [s, DEFAULT_FRAMES[i]]),
));

// atlas geometry
assert.deepEqual(cellRect('review', 0, pet), { x: 0, y: 8 * 208, width: 192, height: 208, row: 8, col: 0 });
assert.deepEqual(cellRect('idle', 5, pet), { x: 5 * 192, y: 0, width: 192, height: 208, row: 0, col: 5 });
assert.deepEqual(lookRect(4, pet), { x: 4 * 192, y: 9 * 208, width: 192, height: 208, row: 9, col: 4, angle: 90 });
assert.deepEqual(lookRect(12, pet), { x: 4 * 192, y: 10 * 208, width: 192, height: 208, row: 10, col: 4, angle: 270 });

// gaze mapping: 0 = up, 90 = right, 180 = down, 270 = left
assert.equal(lookIndexForVector(0, -100), 0);
assert.equal(lookIndexForVector(100, 0), 4);
assert.equal(lookIndexForVector(0, 100), 8);
assert.equal(lookIndexForVector(-100, 0), 12);
assert.equal(lookIndexForVector(1, 1), null);
assert.equal(lookIndexForVector(0, 0), null);
assert.equal(lookIndexForVector(0, 0, 0), null);

// looping idle
const p = new PetPlayer(pet);
const start = p.currentRect();
p.update(1900);
assert.equal(p.state, 'idle');
assert.ok(p.index >= 0 && p.index < 6);
p.setLook(4);
assert.equal(p.currentRect().row, 9);
assert.equal(p.currentRect().col, 4);
p.setLook(null);
assert.equal(p.currentRect().row, 0);

// one-shot waving returns to idle
const q = new PetPlayer(pet);
q.play('waving');
assert.equal(q.state, 'waving');
q.update(10000);
assert.equal(q.state, 'idle');

// one-shot failed also falls back, not looping
const r = new PetPlayer(pet);
r.play('failed');
r.update(10000);
assert.equal(r.state, 'idle');

// third-party extended tracks are honoured
const ext = normalizePet({
  id: 'x',
  spriteVersionNumber: 2,
  frames: { idle: 3 },
  tracks: { idle: { durations: [100, 200, 300], loop: false, fallback: 'waving' } },
});
assert.deepEqual(ext.frames.idle, 3);
assert.equal(ext.tracks.idle.durations.length, 3);
assert.equal(ext.tracks.idle.loop, false);
const s = new PetPlayer(ext);
s.update(700);
assert.equal(s.state, 'waving');

console.log('pet-core: all assertions passed');

// Malformed extensions must not leave a player with NaN geometry or a missing track.
const invalid = new PetPlayer({
  spriteVersionNumber: 2,
  cell: { width: -1, height: 'bad' },
  tracks: { waving: { fallback: 'missing', durations: [Infinity, -10, 100] } },
}, { state: 'missing' });
assert.equal(invalid.state, 'idle');
assert.deepEqual(invalid.pet.cell, { width: 192, height: 208 });
invalid.play('waving');
invalid.update(1000);
assert.equal(invalid.state, 'idle');
invalid.setLook(NaN);
assert.equal(invalid.lookIndex, null);
assert.equal(normalizePet(null).id, 'salt');

// Large time jumps match ordinary incremental playback, without a pending backlog.
const fast = new PetPlayer(ext);
const slow = new PetPlayer(ext);
fast.setState('running-right');
slow.setState('running-right');
fast.update(1234567);
for (let i = 0; i < 12345; i++) slow.update(100);
slow.update(67);
assert.equal(fast.index, slow.index);
assert.equal(fast.elapsed, slow.elapsed);
console.log('pet-core: regression assertions passed');
