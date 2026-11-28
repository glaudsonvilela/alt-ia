import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ConversationWork, unseenDocuments } from './conversation-work.js';

test('concurrent conversations keep their own stream and completion state', () => {
  const requests = new ConversationWork();
  const first = requests.start('first', { id: 'pending-first' });
  first.partial = 'Resposta parcial';
  const second = requests.start('second', { id: 'pending-second' });
  assert.equal(requests.start('first', {}), null);
  requests.finish('second', second);
  assert.equal(requests.busy('first'), true);
  assert.equal(requests.get('first').partial, 'Resposta parcial');
  assert.equal(first.controller.signal.aborted, false);
  requests.finish('first', first, 'Rede indisponível');
  assert.equal(requests.get('first').error, 'Rede indisponível');
  assert.equal(requests.busy('first'), false);
});

test('deleting a chat cancels only its request; stale completion cannot finish a replacement', () => {
  const requests = new ConversationWork();
  const first = requests.start('first', {});
  const second = requests.start('second', {});
  requests.cancel('first');
  assert.equal(first.controller.signal.aborted, true);
  assert.equal(second.controller.signal.aborted, false);
  const replacement = requests.start('first', {});
  requests.finish('first', first);
  assert.equal(requests.get('first'), replacement);
});

test('PDFs appear once across repeated answers; a new conversation has its own cards', () => {
  const a = { kind: 'pdf', id: 'a' }, b = { kind: 'pdf', id: 'b' };
  const seen = new Set();
  assert.deepEqual(unseenDocuments([a, a], seen), [a]);
  assert.deepEqual(unseenDocuments([a, b], seen), [b]);
  assert.deepEqual(unseenDocuments([a]), [a]);
});
