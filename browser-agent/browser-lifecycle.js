// Bound page creation too: a responsive browser process can still have a stuck renderer.
export async function bounded(promise, ms, label) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(label)), ms);
    })]);
  } finally { clearTimeout(timer); }
}

export class BrowserManager {
  constructor(launch, onReset, { creationMs = 4000, closeMs = 2000 } = {}) {
    this.launch = launch;
    this.onReset = onReset;
    this.creationMs = creationMs;
    this.closeMs = closeMs;
    this.browser = null;
    this.queue = Promise.resolve();
  }
  async reset() {
    const previous = this.browser;
    this.browser = null;
    this.onReset();
    if (previous) await bounded(previous.close(), this.closeMs, 'browser_close_timeout').catch(() => {});
  }
  create(setup, register) {
    const result = this.queue.then(async () => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        let context;
        let expired = false;
        try {
          if (this.browser && !this.browser.isConnected()) await this.reset();
          if (!this.browser) this.browser = await this.launch();
          const creation = (async () => {
            context = await this.browser.newContext({ viewport: { width: 1280, height: 720 },
              deviceScaleFactor: 1, acceptDownloads: false, serviceWorkers: 'block', permissions: [] });
            if (expired) { await context.close().catch(() => {}); throw Error('creation_expired'); }
            await setup(context);
            const page = await context.newPage();
            if (expired) { await context.close().catch(() => {}); throw Error('creation_expired'); }
            return { context, page };
          })();
          const created = await bounded(creation, this.creationMs, 'browser_page_timeout');
          // Registration is inside the queue so session capacity checks cannot race.
          try { return register(created); }
          catch (error) { await bounded(context.close(), this.closeMs, 'context_close_timeout').catch(() => {}); throw error; }
        } catch (error) {
          expired = true;
          if (error.code === 'SESSION_CAPACITY') throw error;
          console.warn(JSON.stringify({ event: 'browser_recovery', attempt: attempt + 1, type: error.name }));
          await this.reset();
          if (attempt === 1) throw Error('Não foi possível iniciar o navegador. Tente novamente em instantes.');
        }
      }
    });
    this.queue = result.catch(() => {});
    return result;
  }
}
