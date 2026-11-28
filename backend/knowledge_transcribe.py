"""Read Basecamp video/audio in bounded RAM buffers, retaining only text.

The loopback bridge gives ffmpeg random access without passing Basecamp tokens
or signed URLs in process arguments. There is no local media file/cache.
"""
import json
import array
import math
import os
import secrets
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from knowledge_video import video_response

_whisper = None


@contextmanager
def media_bridge(store, metadata):
    path = '/' + secrets.token_hex(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            if self.path != path:
                self.send_error(404)
                return
            try:
                with video_response(store, metadata, self.headers.get('Range')) as response:
                    self.send_response(response.status_code)
                    for name in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges'):
                        if name in response.headers:
                            self.send_header(name, response.headers[name])
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    for chunk in response.iter_bytes(65536):
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.close_connection = True
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f'http://127.0.0.1:{server.server_port}{path}'
    finally:
        server.shutdown()
        server.server_close()


def transcribe_pcm(pcm, api_key):
    samples = array.array('h', pcm)
    if not samples or max(abs(sample) for sample in samples) < 32:
        return ''
    import numpy as np
    from faster_whisper import WhisperModel
    global _whisper
    if _whisper is None:
        _whisper = WhisperModel(os.environ.get('ALT_IA_WHISPER_MODEL', 'turbo'),
            device='cpu', compute_type='int8', cpu_threads=2, num_workers=1,
            download_root=os.environ.get('ALT_IA_MODEL_CACHE', '/var/cache/alt-ia-models'))
    segments, info = _whisper.transcribe(np.frombuffer(pcm, dtype=np.int16).astype(np.float32)/32768,
        language='pt', beam_size=1, best_of=1, temperature=0.0,
        vad_filter=True, condition_on_previous_text=False)
    return ' '.join(segment.text.strip() for segment in segments)


def timestamp(seconds):
    seconds = int(seconds)
    return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'


def scene_times(url, start, duration):
    """PySceneDetect over a bounded 2fps stream; no video is written to disk."""
    import numpy as np
    from scenedetect.detectors import ContentDetector
    result = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', str(start),
        '-i', url, '-t', str(duration), '-an', '-vf', 'fps=2,scale=320:180', '-pix_fmt', 'bgr24',
        '-f', 'rawvideo', 'pipe:1'], capture_output=True, timeout=120, check=True)
    frame_bytes = 320 * 180 * 3
    detector = ContentDetector(threshold=22, min_scene_len=6)
    frames = len(result.stdout)//frame_bytes
    if not frames:
        raise ValueError('Não foi possível analisar as cenas')
    cuts = {0, min(frames-1,60)}
    for number in range(frames):
        frame = np.frombuffer(result.stdout, np.uint8, frame_bytes, number*frame_bytes).reshape((180,320,3))
        cuts.update(detector.process_frame(number,frame))
    ordered = sorted(cuts)
    # Bound visual-model calls per minute, retaining evenly spaced scene cuts.
    # Audio remains integral; visuals are explicitly marked as sampled.
    if len(ordered) > 4:
        ordered = [ordered[round(i*(len(ordered)-1)/3)] for i in range(4)]
    return [start + max(0, min(duration-.2, number/2 + .5)) for number in ordered]


def read_video(store, metadata, visual, api_key, progress, checkpoint):
    """Full audio plus frames from scene changes and a 30-second fallback."""
    with media_bridge(store, metadata) as url:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
            'format=duration:stream=codec_type', '-of', 'json', url], capture_output=True, timeout=90, check=True)
        info = json.loads(result.stdout)
        duration = float(info['format']['duration'])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Duração do vídeo indisponível')
        has_audio = any(s.get('codec_type') == 'audio' for s in info.get('streams', []))
        has_video = any(s.get('codec_type') == 'video' for s in info.get('streams', []))
        sections = list(progress.get('sections', []))
        start = int(progress.get('seconds', 0))
        for offset in range(start, math.ceil(duration), 60):
            end = min(offset + 60, duration)
            pending = progress.get('pending_interval', {})
            text = pending.get('text') if pending.get('offset') == offset else None
            if not text:
                text = f'[Vídeo {timestamp(offset)}–{timestamp(end)}]'
                if has_audio:
                    pcm = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', str(offset),
                        '-i', url, '-t', str(end-offset), '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', 'pipe:1'],
                        capture_output=True, timeout=120, check=True).stdout
                    if not pcm:
                        raise ValueError('Áudio do intervalo não decodificado')
                    words = transcribe_pcm(pcm, api_key)
                    text += '\n[Transcrição automática; pode conter erros em nomes e números]\n' + (words or '[Sem fala reconhecida neste intervalo]')
                pending = {'offset': offset, 'text': text, 'frames_done': 0}
            def publish_partial():
                pending['text'] = text
                state = {'seconds':offset, 'duration':duration, 'sections':list(sections), 'pending_interval':dict(pending)}
                checkpoint(state, '\n\n'.join([*sections, text]))
            # Make speech searchable before slower visual interpretation finishes.
            publish_partial()
            if has_video:
                if 'frames' not in pending:
                    pending['frames'] = scene_times(url, offset, end-offset)
                for frame_index, frame_at in enumerate(pending['frames']):
                    if frame_index < pending.get('frames_done', 0):
                        continue
                    frame = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', str(frame_at),
                        '-i', url, '-frames:v', '1', '-vf', 'scale=1280:-2', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'],
                        capture_output=True, timeout=90, check=True).stdout
                    if not frame:
                        raise ValueError('Quadro visual não decodificado')
                    text += f'\n[Quadro representativo em {timestamp(frame_at)}; não cobre cada quadro]\n' + visual.read(frame)
                    pending['frames_done'] = frame_index + 1
                    publish_partial()
            sections.append(text)
            progress = {'seconds': offset + 60, 'duration': duration, 'sections': sections}
            checkpoint(progress, '\n\n'.join(sections))
        return ('[Memória do vídeo: áudio percorrido integralmente; PySceneDetect identifica mudanças em amostragem de 2fps, com até quatro quadros representativos por minuto. '
                'Não equivale à leitura de cada quadro; detalhes transitórios podem não estar presentes.]\n\n' + '\n\n'.join(sections))
