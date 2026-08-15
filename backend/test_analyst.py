"""Quick CLI test for the AI analyst — run with: uv run python test_analyst.py"""
import sys
sys.path.insert(0, '.')

from db import get_connection
from ai.analyst import stream_analyst

con = get_connection()
fips = "48169"  # Gaines County — should be CRITICAL

print(f"Streaming Claude analysis for Gaines County ({fips})...\n")
print("-" * 60)

for chunk in stream_analyst(fips, con):
    if not chunk.strip():
        continue
    import json
    raw = chunk.removeprefix("data: ").strip()
    if raw == "[DONE]":
        print("\n" + "-" * 60)
        print("Done.")
        break
    try:
        evt = json.loads(raw)
        if evt["type"] == "text":
            print(evt["delta"], end="", flush=True)
        elif evt["type"] == "error":
            print(f"\nERROR: {evt['message']}", file=sys.stderr)
            sys.exit(1)
    except Exception:
        pass
