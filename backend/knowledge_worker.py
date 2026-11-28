"""Single background worker for encrypted, resumable multimodal knowledge.

Every write reloads under the importer's sync.lock. Jobs run outside that lock;
stale/revoked revisions cannot be committed after a concurrent synchronization.
"""
import argparse
import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from knowledge_store import KnowledgeStore
from knowledge_extract import VisualReader, extract_document
from knowledge_transcribe import read_video


class Superseded(Exception):
    pass


class ContinueLater(Exception):
    pass


class Worker:
    def __init__(self, directory, key_file, api_key):
        self.directory = Path(directory)
        self.key_file = key_file
        self.api_key = api_key
        self.lane = 0
        self.turn = 0

    @contextmanager
    def transaction(self):
        with (self.directory / 'sync.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            store = KnowledgeStore(self.directory / 'knowledge.enc', self.key_file)
            changed = store.db.total_changes
            try:
                yield store
                if store.db.total_changes != changed:
                    store.db.commit()
                    store.save()
            finally:
                store.db.close()

    def reset_interrupted(self):
        with self.transaction() as store, store.db:
            store.db.execute("UPDATE content_jobs SET status='pending',attempts=MAX(0,attempts-1) WHERE status='processing'")

    def claim(self, source=None):
        with self.transaction() as store, store.db:
            rows = store.db.execute("""SELECT j.source_key,j.revision,j.payload,j.progress,j.attempts
                FROM content_jobs j JOIN sources s ON s.source_key=j.source_key
                WHERE j.status IN ('pending','retry') AND j.attempts<3
                ORDER BY CASE WHEN j.payload LIKE '%image/%' THEN 0
                              WHEN j.payload LIKE '%video/%' THEN 2 ELSE 1 END, s.title""").fetchall()
            def rank(row):
                value = json.loads(row[2]); state = json.loads(row[3])
                lane = 0 if value['mime'].startswith('image/') else 1 if value['mime'].startswith('video/') else 2
                requested = store.db.execute('SELECT requested_at FROM content_priority WHERE source_key=?', (row[0],)).fetchone()
                urgent = bool(requested and requested[0] > time.time()-21600 and self.turn % 4 != 3)
                return (not urgent, 0 if urgent else (lane-self.lane)%3,
                        state.get('last_processed',0), 0 if lane == 1 else 1)
            for key, revision, payload, progress, attempts in sorted(rows,key=rank):
                if source and key != source:
                    continue
                state = json.loads(progress)
                if state.get('retry_at', 0) > time.time():
                    continue
                store.db.execute("UPDATE content_jobs SET status='processing',attempts=attempts+1 WHERE source_key=?", (key,))
                self.lane = (self.lane+1)%3
                self.turn += 1
                return key, revision, json.loads(payload), state
        return None

    def update(self, job, *, body=None, status='processing', detail='', progress=None):
        key, revision, payload, _ = job
        with self.transaction() as store, store.db:
            row = store.db.execute('SELECT revision FROM content_jobs WHERE source_key=?', (key,)).fetchone()
            if not row or row[0] != revision or not store.db.execute('SELECT 1 FROM sources WHERE source_key=?', (key,)).fetchone():
                raise Superseded()
            if body is not None:
                store.upsert({**payload['record'], 'body': body})
                if payload['mime'].startswith('video/') or Path(payload['filename']).suffix.lower() in {'.mp4','.mov','.webm','.m4v'}:
                    # Compact UTF-8 text only; media stays at Basecamp. The same
                    # passages are indexed in the encrypted searchable database.
                    store.write_video_text(key, payload['record']['title'], body)
            store.db.execute('UPDATE content_jobs SET status=?,detail=? WHERE source_key=?', (status, detail[:500], key))
            if progress is not None:
                store.db.execute('UPDATE content_jobs SET progress=? WHERE source_key=?', (json.dumps(progress, ensure_ascii=False), key))

    def run_job(self, job):
        key, revision, payload, progress = job
        store = KnowledgeStore(self.directory / 'knowledge.enc', self.key_file)
        def cached(digest):
            store._reload()
            return store.extraction_cached(digest)
        def cache(digest, body):
            with self.transaction() as fresh:
                fresh.cache_extraction(digest, body)
        visual = VisualReader(self.api_key, cached, cache)
        try:
            suffix = Path(payload['filename']).suffix.lower()
            if payload['mime'].startswith('video/') or suffix in {'.mp4', '.mov', '.webm', '.m4v'}:
                def checkpoint(state, body):
                    state['last_processed'] = time.time()
                    self.update(job, body='[Transcrição em andamento; conteúdo parcial]\n' + body,
                        detail=f"Áudio processado: {min(state['seconds'], state['duration']):.0f}/{state['duration']:.0f}s", progress=state)
                    # One minute per turn prevents a long recording from
                    # blocking all other videos/documents in the queue.
                    if state['seconds'] < state['duration'] and state['seconds'] - progress.get('seconds',0) >= 60:
                        raise ContinueLater()
                body = read_video(store, payload, visual, self.api_key, progress, checkpoint)
                detail = 'Áudio integral; até quatro quadros representativos por minuto; transcrição automática.'
            else:
                from basecamp import Client
                from knowledge_video import access_token
                if payload['byte_size'] > 256 * 1024 * 1024:
                    raise ValueError('Arquivo excede a memória de trabalho de 256 MiB')
                with Client(access_token=access_token(store)) as client:
                    account = client.for_account(payload['record']['account_id'])
                    download = account.download_url(payload['download_url'])
                    if len(download.body) > 256 * 1024 * 1024:
                        raise ValueError('Arquivo excede a memória de trabalho de 256 MiB')
                    def document_checkpoint(done, total, sections=None):
                        # Publish completed pages immediately; resume at the next
                        # page instead of rereading the entire prefix every turn.
                        self.update(job, body=('[Leitura parcial: %s/%s páginas]\n' % (done,total) + '\n\n'.join(sections)) if sections else None,
                            detail=f'Páginas/imagens: {done}/{total}', progress={
                            'pages':done,'total':total,'sections': sections or [],'last_processed':time.time()})
                        if done < total and done - progress.get('pages',0) >= 5:
                            raise ContinueLater()
                    body = extract_document(payload['filename'], download.body, visual, document_checkpoint, progress)
                detail = 'Texto e leitura visual extraídos; ambiguidades sinalizadas no conteúdo.'
            if not body.strip():
                raise ValueError('Extração sem texto')
            self.update(job, body=body, status='complete', detail=detail, progress={})
            print(json.dumps({'event': 'indexed', 'source': key, 'characters': len(body)}), flush=True)
        except ContinueLater:
            with self.transaction() as fresh, fresh.db:
                fresh.db.execute("UPDATE content_jobs SET status='pending',attempts=0 WHERE source_key=? AND revision=?", (key,revision))
            print(json.dumps({'event':'checkpoint','source':key}),flush=True)
        except Superseded:
            print(json.dumps({'event': 'superseded', 'source': key}), flush=True)
        except Exception as error:
            # Never log exception messages: network errors may include signed
            # URLs or fragments of documents. Type/status are sufficient for ops.
            try:
                with self.transaction() as fresh:
                    row = fresh.db.execute('SELECT attempts,progress FROM content_jobs WHERE source_key=?', (key,)).fetchone()
                if row:
                    state = json.loads(row[1]); state['retry_at'] = time.time() + 120 * row[0]
                    self.update(job, status='failed' if row[0] >= 3 else 'retry',
                        detail='Extração incompleta: ' + type(error).__name__, progress=state)
            except Superseded:
                pass
            print(json.dumps({'event': 'extraction_error', 'source': key, 'type': type(error).__name__}), flush=True)
        finally:
            store.db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--source', help='Processar somente uma fonte já autorizada/indexada')
    args = parser.parse_args()
    worker = Worker(os.environ.get('ALT_IA_KNOWLEDGE_DIR', '/var/lib/alt-ia/knowledge'),
        os.environ.get('ALT_IA_KNOWLEDGE_KEY_FILE', '/run/secrets/alt-ia-knowledge-key'),
        Path(os.environ.get('ALT_IA_KEY_FILE', '/run/secrets/alt-ia-key')).read_text().strip())
    # Prevent two containers from consuming the same queue after redeploy.
    with (worker.directory / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker.reset_interrupted()
        while True:
            job = worker.claim(args.source)
            if job:
                worker.run_job(job)
            if args.once:
                break
            if not job:
                time.sleep(30)


if __name__ == '__main__':
    main()
