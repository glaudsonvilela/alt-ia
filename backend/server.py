"""Small server-side proxy for the public Alt-IA chat."""

import json
import os
import hashlib
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from simulator import (SimulationInputError, SimulationUnavailable, handle_simulation, is_quant_pool_question,
                       parse_price_shock, pool_chart, pool_options, pool_snapshot, replay_pool_context,
                       simulate_pool_request, simulate_price_shock)
from scenario_tokens import issue, verify


MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
KEY_FILE = os.environ.get("ALT_IA_KEY_FILE", "/run/secrets/alt-ia-key")
HOST = os.environ.get("ALT_IA_HOST", "172.17.0.1")
PORT = int(os.environ.get("ALT_IA_PORT", "8811"))
with open(os.path.join(os.path.dirname(__file__), "ALT_IA.md"), encoding="utf-8") as instructions_file:
    SYSTEM_PROMPT = instructions_file.read()

with open(KEY_FILE, encoding="utf-8") as secret_file:
    API_KEY = secret_file.read().strip()
if not API_KEY.startswith("nvapi-"):
    raise RuntimeError("Chave NVIDIA ausente ou inválida")
SCENARIO_SECRET = hashlib.sha256((API_KEY + ":alt-ia-scenario-v1").encode()).digest()

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
        elif parsed.path == "/api/pool-chart":
            query = parse_qs(parsed.query)
            pool_ids, intervals = query.get("pool_id", []), query.get("interval", [])
            if set(query) != {"pool_id", "interval"} or len(pool_ids) != 1 or len(intervals) != 1 or len(pool_ids[0]) > 120:
                return self.respond(400, {"error": "Parâmetros do gráfico inválidos."})
            try:
                self.respond(200, pool_chart(pool_ids[0], intervals[0]))
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
            scenario_token = payload.get("scenario_token")
            scenario_context = payload.get("scenario_context")
            if scenario_token is not None and (not isinstance(scenario_token, str) or len(scenario_token) > 12000):
                raise ValueError
            if scenario_context is not None and (not isinstance(scenario_context, dict) or len(json.dumps(scenario_context)) > 5000):
                raise ValueError
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
            user_text = messages[-1]["content"]
            if simulation_request is not None:
                simulation = simulate_pool_request(simulation_request)
            else:
                shock = parse_price_shock(user_text)
                if shock is not None:
                    basis = verify(scenario_token, SCENARIO_SECRET)
                    if basis is None and scenario_context is not None:
                        previous = replay_pool_context(scenario_context)
                        basis = (previous or {}).get("simulation", {}).get("_scenario_basis")
                    simulation = simulate_price_shock(basis, shock)
                else:
                    simulation = handle_simulation(user_text)
                    if simulation is None and is_quant_pool_question(user_text):
                        simulation = {"reply": "Para responder com números, preciso da pool, capital, faixa e variação de preço. 📊 Qual pool e cenário você quer calcular?",
                                      "input_request": {"kind": "pool"}}
            if simulation is not None:
                sim_card = simulation.get("simulation")
                if isinstance(sim_card, dict):
                    basis = sim_card.pop("_scenario_basis", None)
                    if basis is not None:
                        simulation["scenario_token"] = issue(basis, SCENARIO_SECRET)
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
            answer = answer.strip()
            if not answer.endswith("?"):
                answer += "\n\n😊 Quer explorar algum ponto ou testar um cenário diferente?"
            self.respond(200, {"reply": answer, "model": MODEL})
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
