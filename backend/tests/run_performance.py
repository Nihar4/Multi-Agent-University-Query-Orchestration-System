"""Performance benchmark.

Measures:
  - Latency of light endpoints (auth, tickets, history, /me) over N requests.
  - Latency of chat by category (smalltalk vs single-dept vs multi-dept).
  - Throughput under K concurrent /tickets requests.

Run:
    .venv\\Scripts\\python.exe -m tests.run_performance
"""
from __future__ import annotations

import argparse
import concurrent.futures
import statistics as stats
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"


def login(email: str, password: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def time_n(label: str, n: int, fn) -> list[float]:
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    summarize(label, samples)
    return samples


def summarize(label: str, samples: list[float]) -> None:
    if not samples:
        print(f"  {label:<32}  no samples")
        return
    s = sorted(samples)
    p50 = s[len(s) // 2]
    p95 = s[max(0, int(len(s) * 0.95) - 1)]
    print(f"  {label:<40}  n={len(samples):>3}  min={min(s)*1000:>6.0f}ms  p50={p50*1000:>6.0f}ms  p95={p95*1000:>6.0f}ms  max={max(s)*1000:>6.0f}ms")


def main() -> int:
    print(f"== Logging in ==")
    alice = login("alice@mock-university.edu", "password123")
    print("   ok\n")

    print("== Light endpoint latency (10 calls each) ==")
    time_n("GET  /health",          10, lambda: httpx.get(f"{BASE}/health", timeout=5))
    time_n("POST /auth/login",      10, lambda: httpx.post(f"{BASE}/auth/login", json={"email": "alice@mock-university.edu", "password": "password123"}, timeout=10))
    time_n("GET  /auth/me",         10, lambda: httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {alice}"}, timeout=10))
    time_n("GET  /tickets",         10, lambda: httpx.get(f"{BASE}/tickets", headers={"Authorization": f"Bearer {alice}"}, timeout=10))
    time_n("GET  /chat/history",    10, lambda: httpx.get(f"{BASE}/chat/history?limit=20", headers={"Authorization": f"Bearer {alice}"}, timeout=10))

    print("\n== Concurrency: 10 parallel GET /tickets ==")
    def _call_tickets():
        return httpx.get(f"{BASE}/tickets", headers={"Authorization": f"Bearer {alice}"}, timeout=10)
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_call_tickets) for _ in range(10)]
        for f in futures:
            r = f.result()
            assert r.status_code == 200
    wall = time.perf_counter() - t0
    print(f"  10 parallel /tickets completed in {wall*1000:.0f}ms  (avg {wall*100:.0f}ms/req)")

    print("\n== Chat latency by category (3 calls each) ==")
    def _chat(q):
        return httpx.post(f"{BASE}/chat", headers={"Authorization": f"Bearer {alice}"},
                          json={"message": q}, timeout=120)

    categories = {
        "smalltalk (no DB, no tools)":  "Thanks!",
        "single-dept + 1 tool call":    "What's my meal plan balance?",
        "single-dept + tool + escalate": "Please open a Housing ticket — I want a different room.",
        "multi-dept (2)":                "Can I get a dorm if I owe tuition?",
    }
    for label, q in categories.items():
        samples = time_n(label, 3, lambda q=q: _chat(q))

    print("\nNote: LLM calls dominate. Light endpoints should be sub-50ms.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE)
    args = parser.parse_args()
    BASE = args.base_url
    sys.exit(main())
