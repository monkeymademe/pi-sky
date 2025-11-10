# Setting Up High-Quality SVG Rendering

To preserve all the detail and quality from the SVG flight card when overlaying it on the map, you need a system library that can render SVG to PNG.

## Quick Setup (macOS)

```bash
# Install Cairo system library
brew install cairo

# Reinstall cairosvg to use the new library
pip install --upgrade cairosvg

# Patch cairocffi to find Homebrew Cairo (required on macOS)
python3 fix_cairo.py
```

After this, running `map_to_png.py` with `--overlay-card` will automatically use the high-quality SVG rendering, preserving all gradients, styling, and details.

**Note**: On macOS with Homebrew, you need to run `fix_cairo.py` once to patch `cairocffi` so it can find the Cairo library in `/opt/homebrew/lib`. This is a one-time setup step.

## Alternative: Linux

```bash
# Install Cairo development libraries
sudo apt-get install libcairo2-dev  # Debian/Ubuntu
# or
sudo yum install cairo-devel        # Red Hat/CentOS
# or
sudo pacman -S cairo                # Arch Linux

# Reinstall cairosvg
pip install --upgrade cairosvg
```

## Current Status

Without Cairo installed, the script will:
1. Try to use cairosvg (fails without Cairo)
2. Try to use svglib (also requires Cairo)
3. Fall back to PIL-based rendering (works, but some detail is lost)

The SVG file is always saved as `test_map_card.svg` for manual conversion if needed.

## Verification

After installing Cairo, run:
```bash
python3 map_to_png.py --lat 52.3667 --lon 13.5033 --track 264.2 \
    --overlay-card --callsign "DLH456" --origin "BER" --destination "CDG" \
    --origin-country "Germany" --destination-country "France" \
    --altitude 37375 --speed 451.4
```

You should see: "Flight card rendered using cairosvg (best quality)"

