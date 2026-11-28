"""Read-only audit of indexed video speech and encrypted text artifacts."""
import argparse
import json
import os
from collections import Counter
from pathlib import Path
from knowledge_store import KnowledgeStore


def video_audit(store):
    store._reload()
    counts = Counter(); jobs = Counter(); rows = []
    known_duration = processed = 0; unknown = exports = 0
    with store.lock:
        videos = store.db.execute('SELECT v.source_key,s.title FROM video_files v JOIN sources s ON s.source_key=v.source_key').fetchall()
        for key, title in videos:
            state = store.content_status(key) or {}
            status = state.get('transcript_status', 'not_indexed')
            counts[status] += 1; jobs[state.get('status','missing')] += 1
            exported = store.video_text_path(key).is_file(); exports += exported
            duration = state.get('duration_seconds')
            if duration:
                known_duration += duration
                processed += duration if status == 'complete' else min(duration,state.get('audio_seconds',0))
            else: unknown += 1
            rows.append({'source':key,'title':title,'audio':status,'seconds':state.get('audio_seconds',0),
                         'duration':duration,'job':state.get('status'),'encrypted_text':exported})
    return {'videos':len(videos),'audio':dict(counts),'jobs':dict(jobs),
            'encrypted_texts':exports,'known_duration_seconds':round(known_duration),
            'processed_audio_seconds':round(processed),'unknown_durations':unknown,
            'all_audio_complete':bool(videos) and counts['complete'] == len(videos) and exports == len(videos),
            'items':rows}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--details',action='store_true');args=parser.parse_args()
    store=KnowledgeStore(Path(os.environ.get('ALT_IA_KNOWLEDGE_DIR','/var/lib/alt-ia/knowledge'))/'knowledge.enc',
        os.environ.get('ALT_IA_KNOWLEDGE_KEY_FILE','/run/secrets/alt-ia-knowledge-key'))
    result=video_audit(store)
    if not args.details: result.pop('items')
    print(json.dumps(result,ensure_ascii=False,indent=2))
