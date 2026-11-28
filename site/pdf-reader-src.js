import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';

GlobalWorkerOptions.workerSrc = '/pdf.worker.js?v=1';

async function loadPdf(id, signal) {
  if (!/^[a-f0-9]{64}$/.test(id)) throw new Error('Documento inválido.');
  const response = await fetch(`/api/knowledge/documents/${id}`, { credentials: 'same-origin', cache: 'no-store', signal });
  if (!response.ok) throw new Error(response.status === 401 ? 'Entre na sua conta para ler este documento.' : 'Não foi possível abrir este documento agora.');
  const data = new Uint8Array(await response.arrayBuffer());
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  const task = getDocument({ data, cMapUrl: '/pdf-assets/cmaps/', cMapPacked: true,
    standardFontDataUrl: '/pdf-assets/standard_fonts/', wasmUrl: '/pdf-assets/wasm/', useWasm: false, isEvalSupported: false,
    isOffscreenCanvasSupported: false, disableWorkerRendering: true,
    enableXfa: false, stopAtErrors: false });
  signal.addEventListener('abort', () => { void task.destroy(); }, { once: true });
  return task.promise;
}

// Only one visible cover is decoded at a time. No PDF or cover is persisted in browser storage.
let coverQueue = Promise.resolve();
const covers = new Map();
export function renderCover(card, canvas, label, id) {
  coverQueue = coverQueue.catch(() => {}).then(async () => {
    if (!card.isConnected) return;
    const cached = covers.get(id);
    if (cached && Date.now() - cached.time < 300000) {
      canvas.width = cached.image.width; canvas.height = cached.image.height;
      canvas.getContext('2d').putImageData(cached.image, 0, 0);
      canvas.hidden = false; label.hidden = true;
      return;
    }
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 25000);
    let pdf;
    try {
      pdf = await loadPdf(id, abort.signal);
      if (!card.isConnected) return;
      const page = await pdf.getPage(1);
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: Math.min(360 / base.width, 440 / base.height) });
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
      covers.set(id, { time: Date.now(), image: canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height) });
      if (covers.size > 12) covers.delete(covers.keys().next().value);
      if (card.isConnected) { canvas.hidden = false; label.hidden = true; }
    } catch { label.textContent = 'PDF · Clique para ler'; }
    finally { clearTimeout(timer); abort.abort(); }
  });
}

export function openReader(dialog, document, close) {
  const abort = new AbortController();
  const stage = dialog.querySelector('.pdf-stage');
  const canvas = dialog.querySelector('canvas');
  const status = dialog.querySelector('.pdf-status');
  const text = dialog.querySelector('.pdf-accessible-text');
  const pageLabel = dialog.querySelector('.pdf-page-label');
  const previous = dialog.querySelector('[data-pdf="previous"]');
  const next = dialog.querySelector('[data-pdf="next"]');
  const zoomOut = dialog.querySelector('[data-pdf="out"]');
  const zoomIn = dialog.querySelector('[data-pdf="in"]');
  let pdf, pageNumber = 1, zoom = 1, renderTask, rendering = Promise.resolve(), revision = 0;
  dialog.querySelector('h2').textContent = document.title;
  canvas.hidden = true;
  text.textContent = '';
  pageLabel.textContent = 'Carregando…';
  status.textContent = 'Abrindo documento…';
  status.hidden = false;
  [previous, next, zoomOut, zoomIn].forEach(button => { button.disabled = true; });
  dialog.showModal();
  const update = () => {
    const ticket = ++revision;
    renderTask?.cancel();
    rendering = rendering.catch(() => {}).then(async () => {
      if (!pdf || abort.signal.aborted || ticket !== revision) return;
      canvas.hidden = true;
      status.textContent = 'Preparando página…';
      status.hidden = false;
      previous.disabled = pageNumber <= 1;
      next.disabled = pageNumber >= pdf.numPages;
      zoomOut.disabled = zoom <= 0.75;
      zoomIn.disabled = zoom >= 2;
      pageLabel.textContent = `${pageNumber} / ${pdf.numPages}`;
      const page = await pdf.getPage(pageNumber);
      if (ticket !== revision || abort.signal.aborted) return;
      const base = page.getViewport({ scale: 1 });
      const width = Math.max(200, stage.clientWidth - 32) * zoom;
      const viewport = page.getViewport({ scale: width / base.width });
      const ratio = Math.min(devicePixelRatio || 1, 1.5, 2400 / viewport.height);
      canvas.width = Math.ceil(viewport.width * ratio);
      canvas.height = Math.ceil(viewport.height * ratio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      renderTask = page.render({ canvasContext: canvas.getContext('2d'), viewport,
        transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] });
      await renderTask.promise;
      if (ticket !== revision || abort.signal.aborted) return;
      canvas.hidden = false;
      status.hidden = true;
      stage.scrollTop = 0;
      const content = await page.getTextContent();
      if (ticket === revision && !abort.signal.aborted) text.textContent = content.items.map(item => item.str || '').join(' ');
    }).catch(error => {
      if (error.name !== 'RenderingCancelledException' && !abort.signal.aborted) {
        status.textContent = 'Não foi possível exibir esta página. Tente a próxima.';
        status.hidden = false;
      }
    });
  };
  const on = (element, event, callback) => element.addEventListener(event, callback, { signal: abort.signal });
  on(previous, 'click', () => { pageNumber = Math.max(1, pageNumber - 1); update(); });
  on(next, 'click', () => { pageNumber = Math.min(pdf.numPages, pageNumber + 1); update(); });
  on(zoomOut, 'click', () => { zoom = Math.max(0.75, zoom - 0.25); update(); });
  on(zoomIn, 'click', () => { zoom = Math.min(2, zoom + 0.25); update(); });
  on(dialog.querySelector('.pool-dialog-close'), 'click', () => close(dialog));
  on(dialog, 'cancel', event => { event.preventDefault(); close(dialog); });
  on(dialog, 'click', event => { if (event.target === dialog) close(dialog); });
  let resizeTimer;
  const observer = new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(update, 150); });
  observer.observe(stage);
  dialog.addEventListener('close', () => {
    abort.abort(); observer.disconnect(); clearTimeout(resizeTimer); renderTask?.cancel();
    canvas.width = canvas.height = 0; text.textContent = ''; pdf = null;
  }, { once: true });
  loadPdf(document.id, abort.signal).then(value => { if (!abort.signal.aborted) { pdf = value; update(); } }).catch(error => {
    if (!abort.signal.aborted) { status.textContent = error.message; pageLabel.textContent = 'Indisponível'; }
  });
}
