// Run the browser entry point against a small DOM boundary, without a browser dependency.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import * as core from './pet-core.js';

let draws = 0;
let lastDraw;
let raf;
class Element {
  constructor() {
    this.children = []; this.dataset = {}; this.style = {}; this.listeners = {};
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  fire(name, event = {}) { for (const fn of this.listeners[name] ?? []) fn({ type: name, ...event }); }
  appendChild(el) { this.children.push(el); }
  setPointerCapture() {} hasPointerCapture() { return false; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 384, height: 416 }; }
  getContext() { return { clearRect() {}, drawImage(...args) { draws++; lastDraw = args; }, fillText() {} }; }
}
const elements = new Map();
const element = (id) => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
const document = { getElementById: element, createElement: () => new Element(),
  body: new Element(), documentElement: new Element(), addEventListener() {} };
const manifest = JSON.parse(await fs.readFile(new URL('../pets/salt/pet.json', import.meta.url)));
const expressions = JSON.parse(await fs.readFile(new URL('../pets/salt/expressions.json', import.meta.url)));
const context = { core, URL, URLSearchParams, performance, document,
  location: { search: '' }, window: { addEventListener() {} },
  fetch: async (url) => ({ ok: /\/(pet|expressions)\.json$/.test(String(url)),
    json: async () => String(url).endsWith('/expressions.json') ? expressions : manifest }),
  Image: class { set src(value) { this.url = value; this.naturalWidth = 1536;
    this.naturalHeight = value.endsWith('/expressions.webp') ? 832 : 2288;
    queueMicrotask(() => this.onload()); } },
  requestAnimationFrame: (fn) => { raf = fn; }, setTimeout: () => 1, clearTimeout() {},
};
let source = await fs.readFile(new URL('app.js', import.meta.url), 'utf8');
source = source.replace(/import\s*\{([\s\S]*?)\}\s*from '\.\/pet-core.js';/, 'const {$1} = core;')
  .replaceAll('import.meta.url', JSON.stringify(import.meta.url));
vm.runInNewContext(source, context);
await new Promise((resolve) => setImmediate(resolve));
const player = context.window.__salt.player;
const stage = element('stage');
const scale = element('scale');
scale.value = '1.5'; scale.fire('input');
assert.equal(stage.style.width, '288px');
stage.fire('pointerdown', { button: 2, isPrimary: true });
assert.equal(context.window.__salt.state.pointerDown, false);
stage.fire('pointerdown', { button: 0, isPrimary: true, screenX: 100, screenY: 100, clientX: 10, clientY: 10 });
// A moving desktop window keeps local coordinates stable: measure screen movement.
stage.fire('pointermove', { screenX: 150, screenY: 150, clientX: 10, clientY: 10 });
stage.fire('pointerup');
assert.equal(player.state, 'idle');
assert.equal(element('pet').style.transform, '');
stage.fire('pointerdown', { button: 0, isPrimary: true, screenX: 100, screenY: 100, clientX: 10, clientY: 10 });
stage.fire('pointerup');
assert.equal(player.state, 'waving');
player.setState('idle');
raf(performance.now());
const previous = draws;
raf(performance.now());
assert.equal(draws, previous, 'unchanged frames should not repaint');
const expressionButtons = element('expressions').children;
assert.equal(expressionButtons.length, 4);
assert.equal(element('expressions-block').hidden, false);
expressionButtons.find((b) => b.dataset.expression === 'cheer').fire('click');
assert.equal(context.window.__salt.state.expression.id, 'cheer');
raf(performance.now());
assert.ok(lastDraw[0].url.endsWith('/expressions.webp'));
assert.equal(lastDraw[2], 0);
player.update(10000);
raf(performance.now());
assert.equal(context.window.__salt.state.expression, null);
assert.ok(lastDraw[0].url.endsWith('/spritesheet.webp'));
expressionButtons.find((b) => b.dataset.expression === 'excited').fire('click');
player.update(10000);
assert.equal(context.window.__salt.state.expression.id, 'excited');
element('states').children.find((b) => b.dataset.state === 'waiting').fire('click');
assert.equal(context.window.__salt.state.expression, null, 'same-track standard selection must restore default sheet');
console.log('app: interaction and render regression assertions passed');
