import test from 'node:test';
import assert from 'node:assert/strict';
import { BrowserManager } from './browser-lifecycle.js';

function fakeBrowser(newPage = async () => ({ ready: true })) {
  return { closed: false, contexts: [], isConnected() { return !this.closed; },
    async close() { this.closed = true; },
    async newContext() {
      const context = { closed: false, newPage, async close() { this.closed = true; } };
      this.contexts.push(context); return context;
    } };
}
const setup = async () => {};
const register = value => value;
test('a renderer stuck during page creation is replaced and retried', async () => {
  const stuck = fakeBrowser(() => new Promise(() => {}));
  const healthy = fakeBrowser();
  let launches = 0, resets = 0;
  const manager = new BrowserManager(async () => ++launches === 1 ? stuck : healthy,
    () => resets++, { creationMs: 15, closeMs: 15 });
  const result = await manager.create(setup, register);
  assert.equal(result.page.ready, true);
  assert.equal(stuck.closed, true);
  assert.equal(launches, 2);
  assert.equal(resets, 1);
});
test('persistent failure is bounded to two attempts', async () => {
  let launches = 0;
  const manager = new BrowserManager(async () => { launches++; return fakeBrowser(() => new Promise(() => {})); },
    () => {}, { creationMs: 10, closeMs: 10 });
  await assert.rejects(manager.create(setup, register), /Não foi possível iniciar/);
  assert.equal(launches, 2);
});
test('simultaneous sessions share one browser and register in order', async () => {
  let launches = 0;
  const manager = new BrowserManager(async () => { launches++; return fakeBrowser(); }, () => {});
  const order = [];
  await Promise.all([1, 2, 3].map(n => manager.create(setup, () => order.push(n))));
  assert.deepEqual(order, [1, 2, 3]);
  assert.equal(launches, 1);
});
test('capacity rejection closes only the extra context', async () => {
  const browser = fakeBrowser();
  let resets = 0;
  const manager = new BrowserManager(async () => browser, () => resets++);
  await assert.rejects(manager.create(setup, () => {
    const error = Error('full'); error.code = 'SESSION_CAPACITY'; throw error;
  }), /full/);
  assert.equal(browser.contexts[0].closed, true);
  assert.equal(browser.closed, false);
  assert.equal(resets, 0);
});
test('disconnected browser is recovered before creating a session', async () => {
  const first = fakeBrowser(), second = fakeBrowser(); let launches = 0;
  const manager = new BrowserManager(async () => ++launches === 1 ? first : second, () => {});
  await manager.create(setup, register); first.closed = true;
  const result = await manager.create(setup, register);
  assert.equal(result.page.ready, true); assert.equal(launches, 2);
});
