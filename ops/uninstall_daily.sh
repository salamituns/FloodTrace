#!/bin/sh
# Remove the FloodTrace daily forecast LaunchAgent (Task 45,
# docs/tasks/45-daily-run.md). Unloads it and deletes that one plist file.
# Nothing else.
set -eu

launchctl bootout "gui/$(id -u)/com.floodtrace.daily" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.floodtrace.daily.plist"
echo "removed $HOME/Library/LaunchAgents/com.floodtrace.daily.plist"
