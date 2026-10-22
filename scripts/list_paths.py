"""列出 OpenAPI 所有路由 — 开发调试用。

用法：先启动 uvicorn，然后 python scripts/list_paths.py
"""
import httpx, json
r = httpx.get("http://127.0.0.1:8000/openapi.json")
spec = r.json()
paths = sorted(spec["paths"].keys())
print(f"Total paths: {len(paths)}")
for p in paths:
    methods = list(spec["paths"][p].keys())
    print(f"  {', '.join(m.upper() for m in methods):12s} {p}")
