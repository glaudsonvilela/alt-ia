// Requests belong to a conversation, never to the currently mounted chat view.
export class ConversationWork {
  constructor() { this.jobs = new Map(); }
  get(id) { return this.jobs.get(id); }
  busy(id) { return this.jobs.get(id)?.status === 'loading'; }
  start(id, node) {
    if (this.busy(id)) return null;
    const job = { node, status: 'loading', partial: '', controller: new AbortController() };
    this.jobs.set(id, job);
    return job;
  }
  finish(id, job, error = '') {
    if (this.get(id) !== job) return;
    if (error) { job.status = 'error'; job.error = error; }
    else this.jobs.delete(id);
  }
  cancel(id) {
    this.get(id)?.controller.abort();
    this.jobs.delete(id);
  }
}

// The first card remains available above; repeated answers need no new copy.
export function unseenDocuments(documents = [], seen = new Set()) {
  return documents.filter(item => {
    const key = `${item.kind}:${item.id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
