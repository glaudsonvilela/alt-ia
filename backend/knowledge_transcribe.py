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
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from knowledge_video import video_response

_whisper = None
_riva_service = None
_nvidia_retry_at = 0
_local_asr_lock = threading.Lock()


def transcribe_nvidia(pcm, api_key):
    """Official NVIDIA Riva Whisper endpoint; raw audio only in RAM."""
    import riva.client
    global _riva_service
    if _riva_service is None:
        auth = riva.client.Auth(use_ssl=True, uri='grpc.nvcf.nvidia.com:443', metadata_args=[
            ['function-id', 'b702f636-f60c-4a3d-a6f4-f3568c13bd7d'],
            ['authorization', 'Bearer ' + api_key]])
        _riva_service = riva.client.ASRService(auth)
    config = riva.client.RecognitionConfig(language_code='pt',
        encoding=riva.client.AudioEncoding.LINEAR_PCM, sample_rate_hertz=16000,
        audio_channel_count=1, max_alternatives=1, enable_automatic_punctuation=True)
    request = riva.client.proto.riva_asr_pb2.RecognizeRequest(config=config, audio=pcm)
    started = time.monotonic()
    response = _riva_service.stub.Recognize(request,
        metadata=_riva_service.auth.get_auth_metadata(), timeout=45)
    print(json.dumps({'event':'asr_nvidia','audio_seconds':round(len(pcm)/32000,1),
                      'elapsed_seconds':round(time.monotonic()-started,2)}),flush=True)
    return ' '.join(result.alternatives[0].transcript.strip() for result in response.results if result.alternatives)



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
    global _nvidia_retry_at
    if os.environ.get('ALT_IA_ASR_PROVIDER') == 'nvidia' and time.monotonic() >= _nvidia_retry_at:
        try:
            return transcribe_nvidia(pcm, api_key)
        except Exception as error:
            # Quotas/outages never discard progress or expose request metadata.
            _nvidia_retry_at = time.monotonic() + 300
            print(json.dumps({'event':'asr_local_fallback','type':type(error).__name__}), flush=True)
    return transcribe_local(pcm)


def transcribe_local(pcm):
    import numpy as np
    from faster_whisper import WhisperModel
    global _whisper
    with _local_asr_lock:
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
        # Audio is a separate pass: slow visual calls must never block the
        # following spoken minute. Old interleaved checkpoints migrate in place.
        sections = list(progress.get('sections', []))
        audio_sections = list(progress.get('audio_sections', sections))
        visual_seconds = progress.get('seconds', 0)
        audio_seconds = progress.get('audio_seconds', visual_seconds)
        pending = dict(progress.get('pending_interval') or {})
        state = {**progress, 'duration':duration, 'has_audio':has_audio, 'has_video':has_video,
                 'seconds':visual_seconds, 'audio_seconds':audio_seconds,
                 'sections':sections, 'audio_sections':audio_sections}

        def publish():
            state['sections'] = list(sections)
            state['audio_sections'] = list(audio_sections)
            # Prefer the visual-enriched prefix, then the remaining audio.
            content = [*sections, *audio_sections[len(sections):]]
            if state.get('pending_interval'):
                p = state['pending_interval']; index = int(p['offset'])//60
                if index < len(content): content[index] = p['text']
            checkpoint(dict(state), '\n\n'.join(content))

        for offset in range(math.ceil(audio_seconds/60)*60, math.ceil(duration), 60):
            end = min(offset + 60, duration)
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
            audio_sections.append(text)
            state['audio_seconds'] = end
            state['audio_complete'] = end >= duration
            publish()

        state['audio_complete'] = True
        for offset in range(math.ceil(visual_seconds/60)*60, math.ceil(duration), 60):
            end = min(offset + 60, duration)
            text = audio_sections[offset//60]
            pending = dict(state.get('pending_interval') or {})
            if pending.get('offset') == offset:
                text = pending['text']
            else:
                pending = {'offset':offset, 'text':text, 'frames_done':0}
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
                    pending.update(text=text, frames_done=frame_index+1)
                    state['pending_interval'] = dict(pending)
                    publish()
            sections.append(text)
            state['seconds'] = end
            state.pop('pending_interval', None)
            publish()
        return ('[Memória do vídeo: áudio percorrido integralmente; PySceneDetect identifica mudanças em amostragem de 2fps, com até quatro quadros representativos por minuto. '
                'Não equivale à leitura de cada quadro; detalhes transitórios podem não estar presentes.]\n\n' + '\n\n'.join(sections))
