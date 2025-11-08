#!/bin/bash
# Wrapper script to run map_to_svg.py with proper library paths for Cairo

# Set library paths for Homebrew Cairo on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:$DYLD_FALLBACK_LIBRARY_PATH"
    export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH"
fi

# Run the Python script with all arguments
exec python3 "$(dirname "$0")/map_to_svg.py" "$@"

