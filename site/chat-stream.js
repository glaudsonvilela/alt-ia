export async function readChatResponse(response, onText) {
  if (!response.headers.get('content-type')?.includes('text/event-stream')) return response.json().catch(() => null);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', result, finished = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const event = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
        for (const line of event.split('\n')) {
          if (!line.startsWith('data:')) continue;
          const payload = JSON.parse(line.slice(5));
          if (payload.error) throw new Error(payload.error);
          if (typeof payload.delta === 'string') onText(payload.delta);
          if (payload.result) { result = payload.result; finished = true; }
        }
      }
      if (finished || done) break;
    }
    if (!finished) throw new Error('A conexão foi interrompida antes de concluir a resposta. Tente novamente.');
    return result;
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
