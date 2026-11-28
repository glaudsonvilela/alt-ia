// Preserve recent turns and the assistant's final choices/questions when a
// long answer needs trimming. Documents are context too, not just decorations.
function fit(text, maximum) {
  if (text.length <= maximum) return text;
  const tail = Math.min(3000, Math.floor(maximum / 3));
  return `${text.slice(0, maximum - tail - 40)}\n[trecho intermediário abreviado]\n${text.slice(-tail)}`;
}

export function conversationMessages(messages) {
  const result = [];
  let remaining = 56000;
  for (const message of messages.slice(-40).reverse()) {
    if (typeof message.text !== 'string' || !['ai', 'user'].includes(message.role)) continue;
    if (message.role === 'ai' && message.text.startsWith('Recebi sua mensagem. A API da Alt-IA ainda')) continue;
    const role = message.role === 'ai' ? 'assistant' : 'user';
    let text = message.followUp ? `${message.text}\n\n${message.followUp}` : message.text;
    if (role === 'assistant' && message.documents?.length) {
      text += '\n[Arquivos mostrados nesta resposta: ' + message.documents.map(item => String(item.title).slice(0, 240)).join('; ') + ']';
    }
    if (remaining < 600) break;
    text = fit(text, Math.min(role === 'assistant' ? 16000 : 4000, remaining));
    if (text) result.unshift({ role, content: text });
    remaining -= text.length;
  }
  return result;
}
