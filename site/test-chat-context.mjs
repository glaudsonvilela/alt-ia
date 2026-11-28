import { test } from 'node:test';
import assert from 'node:assert/strict';
import { conversationMessages } from './chat-context.js';
test('keeps long answers, selected files and the final question', () => {
  const messages = [{role:'user',text:'Estratégias'}, {role:'ai',text:'Explicação '.repeat(2000) + 'Primeira ou segunda?', documents:[{title:'DCA.pdf'}]}, {role:'user',text:'a segunda'}];
  const result = conversationMessages(messages);
  assert.equal(result.length,3);
  assert.ok(result[1].content.length <=16000);
  assert.ok(result[1].content.endsWith('[Arquivos mostrados nesta resposta: DCA.pdf]'));
  assert.ok(result[1].content.includes('Primeira ou segunda?'));
  assert.equal(result[2].content,'a segunda');
});
test('bounds transport while retaining the newest user message', () => {
  const messages=Array.from({length:90},(_,i)=>({role:i%2?'ai':'user',text:'a'.repeat(i%2?18000:4000)}));
  messages.push({role:'user',text:'continue'});
  const result=conversationMessages(messages);
  assert.ok(result.length<=40);
  assert.ok(result.reduce((n,m)=>n+m.content.length,0)<=56000);
  assert.equal(result.at(-1).content,'continue');
});
