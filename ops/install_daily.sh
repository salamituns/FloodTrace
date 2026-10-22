#!/bin/sh
# Install the FloodTrace daily forecast LaunchAgent (Task 45,
# docs/tasks/45-daily-run.md). Fills __REPO__ in the plist template with this
# repo's absolute path, copies it to ~/Library/LaunchAgents/ and loads it.
set -eu

repo=$(cd "$(dirname "$0")/.." && pwd)
src="$repo/ops/com.floodtrace.daily.plist"
dest="$HOME/Library/LaunchAgents/com.floodtrace.daily.plist"

[ -f "$repo/pipeline/.venv/bin/python" ] || {
	echo "missing $repo/pipeline/.venv/bin/python (create the venv first)" >&2
	exit 1
}

mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__REPO__|$repo|g" "$src" > "$dest"

# unload any earlier copy first, so re-running this script is safe
launchctl bootout "gui/$(id -u)/com.floodtrace.daily" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$dest"
echo "installed $dest (runs daily at 06:30 local time)"
