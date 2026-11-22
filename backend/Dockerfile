FROM python:3.12-alpine

COPY requirements.txt /tmp/alt-ia-requirements.txt
RUN pip install --no-cache-dir -r /tmp/alt-ia-requirements.txt && rm /tmp/alt-ia-requirements.txt

CMD ["python", "/app/server.py"]
