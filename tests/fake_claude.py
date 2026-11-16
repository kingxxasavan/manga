#!/usr/bin/env python3
"""Pretends to be the `claude` program. FAKE_CLAUDE_MODE picks what it does."""
import json
import os
import sys
import time

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")


def envelope(result, is_error=False, subtype="success"):
    print(json.dumps({"type": "result", "subtype": subtype, "is_error": is_error, "result": result,
                      "session_id": "abc", "total_cost_usd": 0.01}))


reset = int(time.time()) + 3600
if mode == "ok":
    open("hello.py", "w").write("print('hi from claude')\n")
    envelope("Created hello.py which prints a greeting.")
elif mode == "limit_exit1":
    envelope(f"Claude AI usage limit reached|{reset}", is_error=True, subtype="error_during_execution")
    sys.exit(1)
elif mode == "limit_clean":
    envelope("You've hit your limit · resets 3pm", is_error=True)
elif mode == "limit_plain":
    envelope(f"Claude AI usage limit reached|{reset}")
elif mode == "credit":
    envelope("Credit balance is too low", is_error=True)
    sys.exit(1)
elif mode == "auth":
    envelope("Invalid API key · Please run /login", is_error=True)
    sys.exit(1)
elif mode == "garbage":
    print("Segmentation fault (core dumped)")
    sys.exit(2)
elif mode == "mentions_limit":
    open("limiter.py", "w").write("# rate limiter\n")
    envelope("I built the rate limiter. When the usage limit is reached it returns HTTP 429. " * 5)
