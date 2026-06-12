#!/usr/bin/env bash
# <xbar.title>Personal Systems Dashboard</xbar.title>
# <xbar.version>v2.0</xbar.version>
# <xbar.author>Jeff Curie</xbar.author>
# <xbar.desc>Week hours + social queue status from local dashboard API</xbar.desc>
# <xbar.dependencies>curl,python3</xbar.dependencies>
#
# Install: cp this file to ~/.config/xbar/plugins/ and chmod +x it.
# Refreshes every 1 minute (filename .1m.sh).

API="http://localhost:8765/api/summary"

JSON=$(curl -sf --max-time 3 "$API" 2>/dev/null)

if [ -z "$JSON" ]; then
  echo "⊕ OFFLINE"
  echo "---"
  echo "Dashboard service not running | color=#AA3322"
  echo "Start: docker compose up -d | font=Menlo size=11"
  exit 0
fi

export DASH_JSON="$JSON"

python3 - <<'PYEOF'
import json, os

d = json.loads(os.environ["DASH_JSON"])
total = d["week_total"]
od = d["overdue_count"]

# menu bar title
title = f"⊕ {total}h"
if od:
    title += f" · 📞 {od}"
print(title)
print("---")

print("PERSONAL SYSTEMS | size=12")
print(f"THIS WEEK: {total}h logged | font=Menlo size=11")
for dom in d["domains"]:
    h, g = dom["hours"], dom["goal"]
    width = max(g, h, 4)
    bar = "█" * min(h, width) + "░" * (width - min(h, width))
    goal = f" / {g}h" if g else ""
    warn = " ⚠" if g and h == 0 else ""
    print(f"{dom['key']:<7}{bar} {h}h{goal}{warn} | font=Menlo size=11")

print("---")
if od:
    print(f"SOCIAL — {od} OVERDUE | color=#CC3322 size=11")
    for f in d["overdue"]:
        print(f"{f['name']} (+{f['days']}d) | font=Menlo size=11 color=#CC3322")
else:
    print("SOCIAL — queue clear | size=11")

if d["todos_due"]:
    print("---")
    print("TODOS DUE | size=11")
    for t in d["todos_due"]:
        mark = "⚠ " if t["overdue"] else "• "
        print(f"{mark}{t['text']} ({t['list'].upper()}) | font=Menlo size=11")

print("---")
print("Open Dashboard ↗ | href=http://localhost:8765")
print("Refresh | refresh=true")
PYEOF
