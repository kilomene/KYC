"""Per-key, per-IP and per-flow-token rate limiting (Phase 4 WS3).

Sliding-window counters held in memory by the server process (the
local build is a single process; a multi-process deployment would
move this to shared storage — stated plainly in docs/API.md).
Limits are configured by environment, read when the handler is
built:

    KYC_RL_API_PER_MIN   requests/min per presented API key  (1200)
    KYC_RL_FLOW_PER_MIN  requests/min per flow token         (240)
    KYC_RL_IP_PER_MIN    requests/min per client IP          (6000)
    KYC_RL_WINDOW_SEC    window length in seconds            (60)

Identities are hashes of the presented credential, so unknown or
garbage keys are throttled too (key-guessing is not free). A refused
request gets a real HTTP 429 with a Retry-After header.
"""
import threading, time
from collections import deque

class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._hits = {}  # identity -> deque[monotonic ts]

    def check(self, identity, limit, window):
        """Record one hit for `identity`. Returns (allowed, retry_after).
        limit <= 0 disables that limit (allowed, 0)."""
        if limit is None or limit <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(identity)
            if q is None:
                q = self._hits[identity] = deque()
            cutoff = now - window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                retry = int(q[0] + window - now) + 1
                return False, max(retry, 1)
            q.append(now)
            # Bound memory: drop empty queues opportunistically.
            if len(self._hits) > 10000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            return True, 0

def limits_from_env(env):
    def _int(name, default):
        try:
            return int(env.get(name) or default)
        except (TypeError, ValueError):
            return default
    return {
        "api_per_min": _int("KYC_RL_API_PER_MIN", 1200),
        "flow_per_min": _int("KYC_RL_FLOW_PER_MIN", 240),
        "ip_per_min": _int("KYC_RL_IP_PER_MIN", 6000),
        "window": _int("KYC_RL_WINDOW_SEC", 60),
    }
