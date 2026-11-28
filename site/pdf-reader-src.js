import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';

GlobalWorkerOptions.workerSrc = '/pdf.worker.js?v=1';

// Reuse the same parsed document for its cover and reader. Fetch ranges on
// demand instead of downloading every page before displaying the first one.
const pdfs = new Map();
function trimPdfs() {
  for (const [id, entry] of pdfs) {
    if (pdfs.size <= 3) break;
    if (!entry.users) { clearTimeout(entry.timer); pdfs.delete(id); void entry.task.destroy(); }
  }
}
async function loadPdf(id, signal) {
  if (!/^[a-f0-9]{64}$/.test(id)) throw new Error('Documento inválido.');
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  let entry = pdfs.get(id);
  if (!entry) {
    const task = getDocument({ url: `/api/knowledge/documents/${id}`, withCredentials: true,
      disableStream: true, disableAutoFetch: true, rangeChunkSize: 524288,
      cMapUrl: '/pdf-assets/cmaps/', cMapPacked: true,
      standardFontDataUrl: '/pdf-assets/standard_fonts/', wasmUrl: '/pdf-assets/wasm/', useWasm: false, isEvalSupported: false,
      isOffscreenCanvasSupported: false, disableWorkerRendering: true,
      enableXfa: false, stopAtErrors: false });
    entry = { task, users: 0, timer: null };
    pdfs.set(id, entry);
    task.promise.catch(() => { if (pdfs.get(id) === entry) pdfs.delete(id); });
  }
  clearTimeout(entry.timer);
  entry.users++;
  pdfs.delete(id); pdfs.set(id, entry);
  let released = false;
  const release = () => {
    if (released) return;
    released = true; signal.removeEventListener('abort', release);
    entry.users--;
    if (!entry.users) {
      entry.timer = setTimeout(() => {
        if (pdfs.get(id) === entry && !entry.users) { pdfs.delete(id); void entry.task.destroy(); }
      }, 120000);
      trimPdfs();
    }
  };
  signal.addEventListener('abort', release, { once: true });
  try {
    const pdf = await entry.task.promise;
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    return pdf;
  } catch (error) { release(); throw error; }
}

// Share one decode per document, and paint cached covers synchronously when
// the chat is rebuilt. The cache is memory-only and bounded to 24 covers.
const coverQueues = [Promise.resolve(), Promise.resolve()];
let nextCoverQueue = 0;
const covers = new Map();
const pendingCovers = new Map();
export function paintCachedCover(canvas, label, id) {
  const image = covers.get(id);
  if (!image) return false;
  canvas.width = image.width; canvas.height = image.height;
  canvas.getContext('2d').putImageData(image, 0, 0);
  canvas.hidden = false; label.hidden = true;
  return true;
}
export function renderCover(card, canvas, label, id) {
  if (paintCachedCover(canvas, label, id)) return Promise.resolve();
  if (!pendingCovers.has(id)) {
    const lane = nextCoverQueue++ % coverQueues.length;
    const work = coverQueues[lane].catch(() => {}).then(async () => {
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), 25000);
      try {
        const pdf = await loadPdf(id, abort.signal);
        const page = await pdf.getPage(1);
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: Math.min(360 / base.width, 440 / base.height) });
        const buffer = document.createElement('canvas');
        buffer.width = Math.ceil(viewport.width); buffer.height = Math.ceil(viewport.height);
        await page.render({ canvasContext: buffer.getContext('2d'), viewport }).promise;
        covers.set(id, buffer.getContext('2d').getImageData(0, 0, buffer.width, buffer.height));
        if (covers.size > 24) covers.delete(covers.keys().next().value);
      } finally { clearTimeout(timer); abort.abort(); }
    });
    pendingCovers.set(id, work);
    coverQueues[lane] = work;
    work.finally(() => pendingCovers.delete(id)).catch(() => {});
  }
  return pendingCovers.get(id).then(() => {
    if (card.isConnected) paintCachedCover(canvas, label, id);
  }).catch(() => { if (card.isConnected) label.textContent = 'PDF · Clique para ler'; });
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
      status.textContent = 'Preparando página…';
      status.hidden = !canvas.hidden;
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
      const buffer = window.document.createElement('canvas');
      buffer.width = Math.ceil(viewport.width * ratio);
      buffer.height = Math.ceil(viewport.height * ratio);
      renderTask = page.render({ canvasContext: buffer.getContext('2d'), viewport,
        transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] });
      await renderTask.promise;
      if (ticket !== revision || abort.signal.aborted) return;
      canvas.width = buffer.width; canvas.height = buffer.height;
      canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
      canvas.getContext('2d').drawImage(buffer, 0, 0);
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
  let observedWidth = stage.clientWidth;
  const observer = new ResizeObserver(() => {
    const width = stage.clientWidth;
    if (Math.abs(width - observedWidth) < 2) return;
    observedWidth = width; clearTimeout(resizeTimer); resizeTimer = setTimeout(update, 150);
  });
  observer.observe(stage);
  dialog.addEventListener('close', () => {
    abort.abort(); observer.disconnect(); clearTimeout(resizeTimer); renderTask?.cancel();
    canvas.width = canvas.height = 0; text.textContent = ''; pdf = null;
  }, { once: true });
  loadPdf(document.id, abort.signal).then(value => { if (!abort.signal.aborted) { pdf = value; update(); } }).catch(error => {
    if (!abort.signal.aborted) { status.textContent = error.message; pageLabel.textContent = 'Indisponível'; }
  });
}
