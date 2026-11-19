"""Small server-side proxy for the public Alt-IA chat."""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from simulator import SimulationInputError, SimulationUnavailable, handle_simulation, pool_options, pool_snapshot, simulate_pool_request


MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
KEY_FILE = os.environ.get("ALT_IA_KEY_FILE", "/run/secrets/alt-ia-key")
HOST = os.environ.get("ALT_IA_HOST", "172.17.0.1")
PORT = int(os.environ.get("ALT_IA_PORT", "8811"))
SYSTEM_PROMPT = (
    "Você é a Alt-IA, assistente em português do simulador de blockchain e DeFi Altside. "
    "Ajude a explorar cenários, swaps, pools, lending e riscos com clareza. "
    "O servidor pode calcular prévias de swap USDC/WETH e entrada em algumas pools com o motor Rust do Altside. "
    "Quando houver uma prévia, ela aparece em um cartão separado com bloco e premissas. "
    "Para pedidos fora dessas capacidades, não afirme que executou simulação nem consultou dados atuais. "
    "Você não conecta carteiras nem envia transações. Não dê garantias de retorno."
)

with open(KEY_FILE, encoding="utf-8") as secret_file:
    API_KEY = secret_file.read().strip()
if not API_KEY.startswith("nvapi-"):
    raise RuntimeError("Chave NVIDIA ausente ou inválida")

window = deque()
window_lock = threading.Lock()
slots = threading.BoundedSemaphore(3)


class Handler(BaseHTTPRequestHandler):
    server_version = "AltIA/1.0"

    def log_message(self, format, *args):
        # Do not log prompts, response bodies or credentials.
        pass

    def respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if self.path == "/healthz":
            self.respond(200, {"status": "ok", "model": MODEL})
        elif self.path == "/api/pool-options":
            try:
                self.respond(200, {"pools": pool_options()})
            except SimulationUnavailable as error:
                self.respond(503, {"error": str(error)})
        elif parsed.path == "/api/pool-snapshot":
            query = parse_qs(parsed.query)
            pool_ids = query.get("pool_id", [])
            if set(query) != {"pool_id"} or len(pool_ids) != 1 or len(pool_ids[0]) > 120:
                return self.respond(400, {"error": "Escolha uma pool válida."})
            try:
                self.respond(200, pool_snapshot(pool_ids[0]))
            except SimulationInputError as error:
                self.respond(400, {"error": str(error)})
            except SimulationUnavailable as error:
                self.respond(503, {"error": str(error)})
        else:
            self.respond(404, {"error": "Não encontrado."})

    def do_POST(self):
        if self.path != "/api/chat":
            return self.respond(404, {"error": "Não encontrado."})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.respond(415, {"error": "Envie JSON."})
        origin = self.headers.get("Origin")
        if origin and origin != "https://ai.bigbanana.io":
            return self.respond(403, {"error": "Origem não permitida."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 2 or length > 30000:
            return self.respond(413, {"error": "Mensagem muito longa."})
        try:
            payload = json.loads(self.rfile.read(length))
            raw_messages = payload["messages"]
            simulation_request = payload.get("simulation_request")
            if not isinstance(raw_messages, list) or not 1 <= len(raw_messages) <= 20:
                raise ValueError
            messages = []
            for item in raw_messages:
                role = item["role"]
                content = item["content"]
                if role not in ("user", "assistant") or not isinstance(content, str) or not 1 <= len(content) <= 4000:
                    raise ValueError
                messages.append({"role": role, "content": content})
            if messages[-1]["role"] != "user" or sum(len(m["content"]) for m in messages) > 20000:
                raise ValueError
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            return self.respond(400, {"error": "Conversa inválida."})

        now = time.monotonic()
        with window_lock:
            while window and window[0] < now - 60:
                window.popleft()
            if len(window) >= 30:
                return self.respond(429, {"error": "Muitas mensagens. Aguarde um minuto e tente novamente."})
            window.append(now)
        if not slots.acquire(blocking=False):
            return self.respond(429, {"error": "A Alt-IA está ocupada. Tente novamente em instantes."})
        try:
            simulation = simulate_pool_request(simulation_request) if simulation_request is not None else handle_simulation(messages[-1]["content"])
            if simulation is not None:
                return self.respond(200, simulation)
            request_body = json.dumps({
                "model": MODEL,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                "max_tokens": 2048,
                "temperature": 1,
                "top_p": 0.95,
                "chat_template_kwargs": {"enable_thinking": False},
                "stream": False,
            }).encode("utf-8")
            request = urllib.request.Request(ENDPOINT, request_body, {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }, method="POST")
            with urllib.request.urlopen(request, timeout=90) as upstream:
                result = json.load(upstream)
            answer = result["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Resposta vazia")
            self.respond(200, {"reply": answer.strip(), "model": MODEL})
        except urllib.error.HTTPError as error:
            if error.code == 429:
                self.respond(503, {"error": "O modelo está ocupado. Tente novamente em instantes."})
            elif error.code in (401, 403):
                self.respond(502, {"error": "A conexão com o modelo precisa ser verificada."})
            else:
                self.respond(502, {"error": "O modelo não respondeu agora. Tente novamente."})
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError):
            self.respond(502, {"error": "Não foi possível obter uma resposta. Tente novamente."})
        except SimulationUnavailable as error:
            self.respond(503, {"error": str(error)})
        except SimulationInputError as error:
            self.respond(400, {"error": str(error)})
        finally:
            slots.release()


ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
