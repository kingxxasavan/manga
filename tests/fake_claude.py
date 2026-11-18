#!/usr/bin/env python3
"""Pretends to be the `claude` program. FAKE_CLAUDE_MODE picks what it does."""
import json
import os
import sys
import time

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
log = os.environ.get("FAKE_CLAUDE_LOG")

# The two side questions Anexis asks: how am I signed in, how full is the plan.
if sys.argv[1:3] == ["auth", "status"]:
    method = os.environ.get("FAKE_CLAUDE_AUTH", "claude.ai")
    print(json.dumps({"loggedIn": method != "none", "authMethod": method, "email": "me@example.com", "subscriptionType": "pro"}))
    sys.exit(0 if method != "none" else 1)
if "/usage" in sys.argv:
    percent = os.environ.get("FAKE_CLAUDE_USAGE")
    print(json.dumps({"type": "system", "subtype": "init", "session_id": "abc"}))
    text_percent = os.environ.get("FAKE_CLAUDE_USAGE_TEXT")
    if text_percent is not None:  # what this Claude Code version really prints: plain text
        report = (f"Current session\n  ██████      {text_percent}% used\n  Resets 5pm\n\n"
                  "Current week (all models)\n  ██          12% used\n\nCurrent week (Opus)\n  █████████   99% used\n")
        print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": report}]}}))
    if percent is not None:
        report = {"session": {"total_cost_usd": 0}, "rate_limits": {"limits": [
            {"kind": "session", "group": "session", "percent": float(percent), "resets_at": None, "severity": "ok", "is_active": True},
            {"kind": "weekly_all", "group": "weekly", "percent": 12.0, "resets_at": None, "severity": "ok", "is_active": True},
            {"kind": "weekly_scoped", "group": "weekly", "percent": 99.0, "resets_at": None, "severity": "ok", "is_active": True,
             "scope": {"model": {"display_name": "Fable"}}},
        ]}}
        print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "usage"}]}, "usage_report": report}))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "usage", "session_id": "abc"}))
    sys.exit(0)

if log:
    with open(log, "a") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")


def envelope(result, is_error=False, subtype="success"):
    print(json.dumps({"type": "result", "subtype": subtype, "is_error": is_error, "result": result,
                      "session_id": "abc", "total_cost_usd": 0.01}))


reset = int(time.time()) + 3600
noted = os.environ.get("FAKE_CLAUDE_RUN_UTILIZATION")
if noted is not None:  # the usage note Claude Code sends while it works
    print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning", "utilization": float(noted), "resetsAt": reset}}))
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
