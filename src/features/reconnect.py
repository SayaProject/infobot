# Reconnection Manager with Exponential Backoff
import time
import random

def retry_with_backoff(fn, max_retries=5):
    for i in range(max_retries):
        try:
            return fn()
        except Exception:
            time.sleep((2 ** i) + random.uniform(0, 1))

# Timestamp: 2026-08-17T09:33:03.688Z
