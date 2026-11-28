"""Resolve one HTTP byte range, including suffix and open-ended requests."""
from knowledge_video import range_header


def byte_window(header, size):
    if not header:
        return 0, size
    value = range_header(header).removeprefix('bytes=')
    first, last = value.split('-')
    if not first:
        start, stop = max(0, size - int(last)), size
    else:
        start, stop = int(first), min(size, int(last) + 1) if last else size
    if start >= size or stop <= start:
        raise ValueError('Intervalo fora do documento')
    return start, stop
