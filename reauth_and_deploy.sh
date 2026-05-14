#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== Yahoo session reauth ==="
python3 sync/yahoo_playwright.py --reauth

echo ""
echo "=== SCP to Pi5 ==="
scp yahoo_session.json pi@pi5-1.local:~/fantasy-baseball/

echo ""
echo "Done. Pi5 session updated."
