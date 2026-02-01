#!/bin/bash
# Monitor Panel server logs in real-time

echo "=== Panel Server Status ==="
if pgrep -f "panel serve" > /dev/null; then
    echo "✓ Server is RUNNING (PID: $(pgrep -f 'panel serve'))"
    echo "✓ URL: http://localhost:5006/app"
else
    echo "✗ Server is NOT running"
    echo "  Start with: .venv/bin/python -m panel serve app.py --show"
    exit 1
fi

echo ""
echo "=== Recent Logs (Last 50 lines) ==="
echo "======================================="
tail -50 panel_server.log

echo ""
echo "=== Live Log Monitoring ==="
echo "Press Ctrl+C to stop monitoring"
echo "======================================="
tail -f panel_server.log
