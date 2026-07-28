# Dev server: serves static files + proxies /api/* to the deployed Modal backend
import http.server
import urllib.request
import os
import sys

BACKEND = "https://bassyj32--trimaura-fastapi-app.modal.run"
PORT = 8100

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/") or self.path == "/health":
            # Proxy to backend
            try:
                url = BACKEND + self.path
                req = urllib.request.Request(url, headers={"User-Agent": "TrimAURA-Dev"})
                resp = urllib.request.urlopen(req)
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
            except Exception as e:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error":"proxy error: {str(e)}"}}'.encode())
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b""
                url = BACKEND + self.path
                req = urllib.request.Request(url, data=body, method="POST",
                    headers={"Content-Type": self.headers.get("Content-Type", "application/json"),
                             "User-Agent": "TrimAURA-Dev"})
                resp = urllib.request.urlopen(req)
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
            except Exception as e:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error":"proxy error: {str(e)}"}}'.encode())
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(__file__), "public"))
    server = http.server.HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"Dev server: http://localhost:{PORT}")
    print(f"Proxying /api/* -> {BACKEND}")
    server.serve_forever()
