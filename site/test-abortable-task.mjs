import test from 'node:test';
import assert from 'node:assert/strict';
import { abortable } from './abortable-task.js';

test('a stalled PDF releases the lane so the next cover can render', async () => {
  const abort = new AbortController();
  let rendered = false;
  const lane = abortable(new Promise(() => {}), abort.signal);
  const next = lane.catch(() => {}).then(() => { rendered = true; });
  abort.abort();
  await assert.rejects(lane, { name: 'AbortError' });
  await next;
  assert.equal(rendered, true);
});
test('aborted work cannot later publish a stale result', async () => {
  const abort = new AbortController(); let complete; let published = false;
  const pending = abortable(new Promise(resolve => { complete = resolve; }), abort.signal).then(() => { published = true; });
  abort.abort(); complete('obsolete cover');
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(published, false);
});
test('a ready PDF is returned normally', async () => {
  assert.equal(await abortable(Promise.resolve('cover'), new AbortController().signal), 'cover');
});
