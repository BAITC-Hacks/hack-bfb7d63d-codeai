"""Local HTTP API. No external services, persistence outside the workspace or account actions."""
from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit
import uuid

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
INPUT_NAMES = {"nodes.parquet", "edges.parquet", "transactions.parquet"}
EXPORT_NAMES = {"nodes_roles.csv", "clusters.csv", "top_nodes.csv", "analysis.json"}
MAX_BODY_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 24 * 1024 * 1024


def simulate(analysis: dict, gids: list) -> dict:
    """Remove nodes from the observed graph and report structural effects only."""
    if not isinstance(gids, list) or not gids or len(gids) > 100:
        raise ValueError("Choose between 1 and 100 node IDs for the simulation.")
    if any(isinstance(gid, bool) or not (isinstance(gid, int) or
           (isinstance(gid, str) and re.fullmatch(r"-?\d{1,20}", gid))) for gid in gids):
        raise ValueError("Every gid must be an integer.")
    existing = {int(node["gid"]) for node in analysis["nodes"]}
    removed = {int(gid) for gid in gids}
    if not removed <= existing:
        raise ValueError("Simulation contains an unknown gid.")
    graph = nx.DiGraph()
    graph.add_nodes_from(existing)
    graph.add_edges_from((int(e["src"]), int(e["dst"])) for e in analysis["edges"])
    seeds = {int(n["gid"]) for n in analysis["nodes"] if n["is_seed"]}

    def reachable(g, starts):
        visited = set(starts) & set(g)
        pending = list(visited)
        while pending:
            for neighbor in g.successors(pending.pop()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        return visited

    def snapshot(g, reachable_set):
        components = list(nx.weakly_connected_components(g))
        return {"n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges(),
                "components": len(components), "largest_component": max(map(len, components), default=0),
                "reachable_from_seeds": len(reachable_set)}

    reachable_before = reachable(graph, seeds)
    before = snapshot(graph, reachable_before)
    graph.remove_nodes_from(removed)
    reachable_after = reachable(graph, seeds - removed)
    after = snapshot(graph, reachable_after)
    return {"removed": [str(gid) if abs(gid) > 9007199254740991 else gid for gid in sorted(removed)], "before": before, "after": after,
            "lost_reachable": len(reachable_before - removed - reachable_after),
            "observed_flow_removed_kzt": round(sum(float(e["sum_kzt"]) for e in analysis["edges"]
                                                  if int(e["src"]) in removed or int(e["dst"]) in removed), 2),
            "note": "Бұл — көрінетін графтың құрылымдық симуляциясы. Ақшаның тоқтауын, нақты бұғаттауды немесе желінің бейімделуін болжамайды."}


def simulate_request(analysis: dict, body: dict) -> dict:
    """A reproducible top-priority removal experiment, including every prefix."""
    if "top_n" in body and "gids" in body:
        raise ValueError("Choose either top_n or gids, not both.")
    curve = body.get("curve", False)
    if not isinstance(curve, bool):
        raise ValueError("curve must be boolean.")
    if "top_n" in body:
        count = body["top_n"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
            raise ValueError("top_n must be an integer between 1 and 100.")
        ordered = sorted(analysis["nodes"], key=lambda node: (-node.get("priority_score", 0), int(node["gid"])))
        gids = [node["gid"] for node in ordered[:count]]
        if not gids:
            raise ValueError("The graph is empty; no nodes can be removed.")
    else:
        gids = body.get("gids")
    result = simulate(analysis, gids)
    # Validate before deduplication; keep the requested removal order for prefixes.
    unique = list(dict.fromkeys(int(gid) for gid in gids))
    result["selection"] = "top_priority" if "top_n" in body else "explicit"
    result["requested_n"] = body.get("top_n", len(unique))
    result["actual_n"] = len(unique)
    if curve:
        result["curve"] = [{"n": 0, "before": result["before"], "after": result["before"],
                            "lost_reachable": 0, "observed_flow_removed_kzt": 0, "removed": []}]
        for n in range(1, len(unique) + 1):
            point = simulate(analysis, unique[:n])
            result["curve"].append({"n": n, **point})
    return result


class ApplicationState:
    def __init__(self, analysis, output_dir, store_dir=None):
        self.analysis = analysis
        self.output_dir = Path(output_dir).resolve()
        self.lock = threading.Lock()
        self.processing = threading.Lock()
        self.store_dir = Path(store_dir) if store_dir else self.output_dir / "investigations"

    def _investigation_file(self, suffix):
        from .review import dataset_fingerprint
        return self.store_dir / (dataset_fingerprint(self.analysis) + suffix)

    def _checked_payload(self, payload):
        from .review import dataset_fingerprint
        result = dict(payload)
        expected = result.pop("expected_dataset_fingerprint", None)
        if expected is not None and expected != dataset_fingerprint(self.analysis):
            raise ValueError("Деректер жиыны өзгерді. Бетті жаңартып, жазбаны қайта тексеріңіз.")
        return result

    @staticmethod
    def _save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def reviews(self, payload=None):
        from .review import empty_casebook, update_review
        with self.lock:
            if payload is not None:
                payload = self._checked_payload(payload)
            path = self._investigation_file(".reviews.json")
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty_casebook(self.analysis)
            result = update_review(self.analysis, existing, payload or {"action": "refresh"})
            if payload:
                self._save(path, result)
            return result

    def expansion(self, payload=None):
        from .expansion import expand_analysis
        with self.lock:
            if payload is not None:
                payload = self._checked_payload(payload)
            path = self._investigation_file(".expansion.json")
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            if payload is None:
                return existing or {"available": False}
            result = expand_analysis(existing["graph"] if existing else self.analysis, payload)
            result["available"] = True
            self._save(path, result)
            return result

    def graph_for_scope(self, scope="base"):
        if scope == "base":
            return self.snapshot()[0]
        if scope == "expanded":
            result = self.expansion()
            if not result.get("available"):
                raise ValueError("Қосымша дерек әлі жүктелген жоқ.")
            return result["graph"]
        raise ValueError("scope must be base or expanded")

    def snapshot(self):
        with self.lock:
            return self.analysis, self.output_dir

    def run_analysis(self, data_dir, output_dir, *, demo):
        from .pipeline import analyze
        result = analyze(data_dir, output_dir, demo=demo)
        with self.lock:
            self.analysis, self.output_dir = result, Path(output_dir).resolve()
        return result


def make_handler(state: ApplicationState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AqshaTrace/1.0"

        def log_message(self, format, *args):
            # Request paths only; never dump transaction content.
            print("[local] " + format % args, flush=True)

        def respond(self, status, body, content_type="application/json; charset=utf-8", filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def error(self, status, message):
            self.respond(status, {"error": str(message)})

        def allowed_host(self):
            host = self.headers.get("Host", "")
            return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self.allowed_host():
                return self.error(403, "This application is available on localhost only.")
            path = urlsplit(self.path).path
            if path == "/api/analysis":
                return self.respond(200, state.snapshot()[0])
            if path == "/api/health":
                return self.respond(200, {"status": "ok"})
            if path == "/api/assistant/status":
                from .local_llm import model_status
                return self.respond(200, model_status())
            if path in {"/api/reviews", "/api/reviews/template.csv", "/api/reviews/export.json", "/api/expansion"}:
                try:
                    if path == "/api/expansion":
                        return self.respond(200, state.expansion())
                    if path == "/api/reviews/template.csv":
                        from .review import labels_csv_template
                        text = labels_csv_template(state.snapshot()[0]).encode("utf-8-sig")
                        return self.respond(200, text, "text/csv; charset=utf-8", filename="verified-roles-template.csv")
                    result = state.reviews()
                    return self.respond(200, result, filename="review-evidence.json" if path.endswith("export.json") else None)
                except (ValueError, OSError) as exc:
                    return self.error(400, str(exc))
            if path == "/api/report.pdf":
                try:
                    from .reports import build_report
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if set(query) - {"gid"} or len(query.get("gid", [])) > 1:
                        raise ValueError("Use one optional gid for the report.")
                    gid = query.get("gid", [None])[0]
                    pdf = build_report(state.snapshot()[0], gid=gid)
                    return self.respond(200, pdf, "application/pdf", filename="aqsha-trace-report.pdf")
                except ValueError as exc:
                    return self.error(400, str(exc))
                except Exception:
                    import traceback
                    traceback.print_exc()
                    return self.error(500, "Report generation failed. See the local terminal for details.")
            if path.startswith("/api/download/"):
                name = path.removeprefix("/api/download/")
                if name not in EXPORT_NAMES:
                    return self.error(404, "Unknown export.")
                _, output_dir = state.snapshot()
                target = output_dir / name
                if not target.is_file():
                    return self.error(404, "Export unavailable.")
                content_type = "application/json; charset=utf-8" if name.endswith(".json") else "text/csv; charset=utf-8"
                return self.respond(200, target.read_bytes(), content_type, filename=name)
            # Fixed static route allowlist prevents arbitrary workspace file access.
            static_files = {"/": "index.html", "/index.html": "index.html", "/favicon.svg": "favicon.svg",
                            "/app.js": "app.js", "/styles.css": "styles.css", "/style.css": "style.css"}
            relative = static_files.get(path)
            if not relative:
                return self.error(404, "Not found.")
            target = WEB / relative
            if not target.is_file():
                return self.error(404, "Interface file unavailable.")
            media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".js":
                media_type = "text/javascript"
            return self.respond(200, target.read_bytes(), media_type + "; charset=utf-8")

        def read_json(self):
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected application/json.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Invalid request length.") from exc
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError("Request must contain JSON and be smaller than 64 MiB.")
            try:
                body = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid JSON.") from exc
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object.")
            return body

        def do_POST(self):
            if not self.allowed_host():
                return self.error(403, "This application is available on localhost only.")
            origin = self.headers.get("Origin")
            allowed_origins = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if origin and origin not in allowed_origins:
                return self.error(403, "Cross-origin requests are disabled.")
            path = urlsplit(self.path).path
            if path not in {"/api/demo", "/api/analyze", "/api/simulate", "/api/assistant", "/api/reviews", "/api/expand", "/api/explore", "/api/recovery"}:
                return self.error(404, "Not found.")
            try:
                body = self.read_json()
                if path == "/api/simulate":
                    return self.respond(200, simulate_request(state.snapshot()[0], body))
                if path == "/api/assistant":
                    mode = body.get("mode", "local_rules")
                    if mode == "local_llm":
                        from .local_llm import answer_with_model, LocalModelUnavailable
                        try:
                            return self.respond(200, answer_with_model(state.snapshot()[0], body.get("question"), gid=body.get("gid")))
                        except LocalModelUnavailable as exc:
                            return self.error(503, str(exc))
                    if mode != "local_rules":
                        raise ValueError("mode must be local_rules or local_llm")
                    from .assistant import answer_question
                    return self.respond(200, answer_question(state.snapshot()[0], body.get("question"), gid=body.get("gid")))
                if path == "/api/reviews":
                    return self.respond(200, state.reviews(body))
                if path == "/api/expand":
                    return self.respond(200, state.expansion(body))
                if path == "/api/explore":
                    from .exploration import explore_paths
                    graph = state.graph_for_scope(body.get("scope", "base"))
                    return self.respond(200, explore_paths(graph, {key: value for key, value in body.items() if key != "scope"}))
                if path == "/api/recovery":
                    from .recovery import recovery_scenario
                    return self.respond(200, recovery_scenario(state.snapshot()[0], body))
                if not state.processing.acquire(blocking=False):
                    return self.error(409, "Another analysis is running. Try again shortly.")
                try:
                    run_id = uuid.uuid4().hex
                    data_dir = ROOT / "data" / "uploads" / run_id
                    output_dir = ROOT / "output" / "runs" / run_id
                    if path == "/api/demo":
                        from .demo import generate_demo
                        generate_demo(data_dir)
                    else:
                        files = body.get("files")
                        if not isinstance(files, dict) or set(files) != INPUT_NAMES:
                            raise ValueError("Upload exactly nodes.parquet, edges.parquet and transactions.parquet.")
                        decoded = {}
                        for name in sorted(INPUT_NAMES):
                            if not isinstance(files[name], str):
                                raise ValueError("File content must be base64 text.")
                            try:
                                content = base64.b64decode(files[name], validate=True)
                            except (binascii.Error, ValueError) as exc:
                                raise ValueError(f"Invalid base64 for {name}.") from exc
                            if not 8 <= len(content) <= MAX_FILE_BYTES or content[:4] != b"PAR1" or content[-4:] != b"PAR1":
                                raise ValueError(f"{name} must be a valid Parquet file smaller than 24 MiB.")
                            decoded[name] = content
                        data_dir.mkdir(parents=True, exist_ok=False)
                        for name, content in decoded.items():
                            (data_dir / name).write_bytes(content)
                    result = state.run_analysis(data_dir, output_dir, demo=path == "/api/demo")
                    return self.respond(200, result)
                finally:
                    state.processing.release()
            except (ValueError, FileNotFoundError) as exc:
                return self.error(400, str(exc))
            except Exception:
                import traceback
                traceback.print_exc()
                return self.error(500, "Analysis failed. See the local terminal for details; the previous result is preserved.")

    return Handler


def serve(analysis, output_dir, *, port=8765):
    state = ApplicationState(analysis, output_dir, store_dir=ROOT / "data" / "investigations")
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    server.daemon_threads = True
    print(f"AQSHA TRACE: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
