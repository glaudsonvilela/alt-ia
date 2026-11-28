import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readChatResponse} from './chat-stream.js';
const response=text=>new Response(new ReadableStream({start(controller){const bytes=new TextEncoder().encode(text);for(let i=0;i<bytes.length;i+=3)controller.enqueue(bytes.slice(i,i+3));controller.close();}}),{headers:{'Content-Type':'text/event-stream'}});
test('handles split unicode and final cards',async()=>{
 const events=[{delta:'Olá 💡'},{delta:' reserva'},{result:{reply:'Olá 💡 reserva',documents:[{id:'abc'}]}}];
 let partial='';const result=await readChatResponse(response(events.map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')),d=>partial+=d);
 assert.equal(partial,result.reply);assert.equal(result.documents.length,1);
});
test('fails disconnected and error streams instead of saving incomplete text',async()=>{
 await assert.rejects(readChatResponse(response('data: {"delta":"partial"}\n\n'),()=>{}),/interrompida/);
 await assert.rejects(readChatResponse(response('data: {"error":"Falhou"}\n\n'),()=>{}),/Falhou/);
});
test('still handles JSON routes',async()=>{assert.equal((await readChatResponse(new Response('{"reply":"News"}'),()=>{})).reply,'News');});
