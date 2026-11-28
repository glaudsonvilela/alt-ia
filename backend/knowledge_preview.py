"""Small native Basecamp posters; originals never downloaded. Cache is encrypted."""
import hashlib
import threading
from urllib.parse import urlsplit, urlunsplit, urljoin

import httpx
from knowledge_store import decrypt, encrypt, private_write
from knowledge_video import access_token, signed_destination, REDIRECTS

_slots = threading.BoundedSemaphore(3)
_locks = [threading.Lock() for _ in range(32)]
MIMES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}


def preview_origin(url):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in {'preview.app.basecamp.com','3.basecampapi.com'}
            or parts.port not in (None,443) or parts.username or parts.password or '/blobs/' not in parts.path):
        raise ValueError('Origem de capa inválida')
    return urlunsplit(('https','3.basecampapi.com',parts.path,parts.query,''))


def video_preview(store, identifier):
    # Authorization/source existence is checked even when the image is cached.
    url = store.get_video_preview(identifier)
    if not url:
        return None
    origin = preview_origin(url)
    digest = hashlib.sha256(url.encode()).hexdigest()
    path = store.path.parent / 'previews' / (digest + '.enc')
    with _locks[int(digest[:2],16)%len(_locks)]:
        if path.exists():
            mime, body = decrypt(store.key,path.read_bytes()).split(b'\n',1)
            return mime.decode(),body
        if not _slots.acquire(timeout=2):
            raise TimeoutError('Capas ocupadas')
        try:
            headers={'User-Agent':'Alt-IA Basecamp preview','Accept-Encoding':'identity',
                     'Authorization':'Bearer '+access_token(store)}
            with httpx.Client(timeout=12,follow_redirects=False) as client:
                target = origin
                for hop in range(3):
                    with client.stream('GET',target,headers=headers) as response:
                        if response.status_code in REDIRECTS:
                            target = signed_destination(urljoin(target,response.headers.get('location','')))
                            headers.pop('Authorization',None)
                            continue
                        mime=response.headers.get('content-type','').split(';')[0].lower()
                        if response.status_code != 200 or mime not in MIMES:
                            raise ValueError('Capa indisponível')
                        chunks=[];size=0
                        for chunk in response.iter_bytes(65536):
                            size+=len(chunk)
                            if size > 2*1024*1024:
                                raise ValueError('Capa excede limite')
                            chunks.append(chunk)
                        body=b''.join(chunks)
                        private_write(path,encrypt(store.key,mime.encode()+b'\n'+body))
                        return mime,body
                raise ValueError('Redirecionamento de capa inválido')
        finally:
            _slots.release()
