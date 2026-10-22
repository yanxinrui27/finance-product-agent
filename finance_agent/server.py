"""单用户回环 HTTP 服务；不适合直接暴露到局域网或公网。"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit

from .artifacts import export_bundle, prototype
from .core import Conflict, Store, evaluate, validate
from .drafts import generate, start_workspace

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "finance_agent/static"


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, database, enable_local_ai=False):
        self.store = Store(database)
        self.enable_local_ai = enable_local_ai
        self.csrf = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    timeout = 10
    def log_message(self, format, *args):
        # 不在日志记录 URL、请求体、模型提示词或客户内容。
        pass

    def respond(self, status, payload, mime="application/json; charset=utf-8", filename=None):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, str):
            payload = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if self.path == "/prototype":
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        else:
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(payload)

    def permitted(self, writing=False):
        error = None
        if self.headers.get("Host") != urlsplit(self.server.origin).netloc:
            error = "拒绝非本机 Host"
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            error = "拒绝跨站请求"
        if writing and not secrets.compare_digest(self.headers.get("X-FPA-CSRF", ""), self.server.csrf):
            error = "写入凭据无效，请从本机页面操作"
        if error:
            # Windows 上未消费小请求体就关闭 socket 可能丢失 403 响应。
            if writing:
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if 0 < size <= 2_000_000:
                        self.rfile.read(size)
                except (ValueError, OSError):
                    pass
            self.respond(403, {"error": error})
            return False
        return True

    def do_GET(self):
        if not self.permitted():
            return
        try:
            if self.path == "/":
                page = (STATIC / "index.html").read_text(encoding="utf-8").replace("__CSRF__", self.server.csrf)
                return self.respond(200, page, "text/html; charset=utf-8")
            assets = {"/app.js": "text/javascript; charset=utf-8", "/style.css": "text/css; charset=utf-8"}
            if self.path in assets:
                return self.respond(200, (STATIC / self.path[1:]).read_bytes(), assets[self.path])
            if self.path == "/api/state":
                return self.respond(200, {**self.server.store.current(), "local_ai_enabled": self.server.enable_local_ai})
            if self.path == "/api/history":
                return self.respond(200, self.server.store.history())
            if self.path == "/api/example":
                return self.respond(200, json.loads((ROOT / "examples/demo.json").read_text(encoding="utf-8")))
            if self.path in ("/api/export", "/prototype"):
                state = self.server.store.current()
                if not state["data"]:
                    raise ValueError("请先保存一个版本")
                if self.path == "/prototype":
                    return self.respond(200, prototype(state), "text/html; charset=utf-8")
                return self.respond(200, export_bundle(state, self.server.store.history()), "application/zip", f"finance-product-v{state['version']}.zip")
            return self.respond(404, {"error": "不存在的路径"})
        except ValueError as error:
            self.respond(400, {"error": str(error)})

    def do_POST(self):
        if not self.permitted(writing=True):
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 2_000_000 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("请求必须为不超过2MB的 JSON")
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError("请求必须为 JSON 对象")
            store = self.server.store
            if self.path == "/api/save":
                result = store.save(value["data"], value["version"], value["actor"], value["reason"])
            elif self.path == "/api/approve":
                result = store.approve(value["version"], value["actor"])
            elif self.path == "/api/new":
                result = start_workspace(value["title"], value["brief"], value["owner"])
            elif self.path == "/api/validate":
                validate(value["data"])
                result = {"valid": True}
            elif self.path in ("/api/evaluate", "/api/draft"):
                current = store.current()
                if current["version"] != value["version"]:
                    raise Conflict("版本已变化，请重新载入")
                if current["data"] is None:
                    raise ValueError("请先保存工作区")
                if self.path == "/api/draft":
                    result = {"draft": generate(current["data"], value["model"], self.server.enable_local_ai), "version": current["version"], "status": "待人工复核，未写入任何正式条目"}
                else:
                    rule = next((r for r in current["data"]["rules"] if r["id"] == value["rule_id"]), None)
                    if rule is None:
                        raise ValueError("规则不存在")
                    result = {"result": evaluate(rule, value["amount"], value["currency"], value["date"]), "version": current["version"], "rule_id": rule["id"], "note": "这是配置规则试算，不代表实际系统 UAT 通过"}
            else:
                return self.respond(404, {"error": "不存在的接口"})
            self.respond(200, result)
        except Conflict as error:
            self.respond(409, {"error": str(error)})
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
            message = "请求字段或数据类型不完整" if isinstance(error, (TypeError, KeyError)) else str(error)
            self.respond(400, {"error": message})
        except sqlite3.Error:
            self.respond(500, {"error": "数据库操作失败，本次未保存；请检查本地磁盘和权限"})


def main():
    parser = argparse.ArgumentParser(description="Finance Product Agent 本地工作台")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", type=Path, default=ROOT / "data/workspace.sqlite")
    parser.add_argument("--enable-local-ai", action="store_true", help="允许逐次点击调用本机 Ollama；不启用云模型")
    args = parser.parse_args()
    with LocalServer(args.port, args.database, args.enable_local_ai) as server:
        print(f"Finance Product Agent 已启动：{server.origin}；仅本机可访问。Ctrl+C 停止。", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
