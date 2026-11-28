// AbortSignal alone does not reject PDF.js promises. Bound the wait explicitly
// so a stalled document cannot occupy a cover queue indefinitely.
export function abortable(promise, signal) {
  return new Promise((resolve, reject) => {
    const aborted = () => reject(new DOMException('Aborted', 'AbortError'));
    if (signal.aborted) { aborted(); return; }
    signal.addEventListener('abort', aborted, { once: true });
    Promise.resolve(promise).then(resolve, reject).finally(() => signal.removeEventListener('abort', aborted));
  });
}
