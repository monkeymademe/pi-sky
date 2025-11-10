#!/usr/bin/env python3
"""
Display an image on the Inky Impression 7.3" display

This script loads an image file and displays it on the connected Inky Impression display.
Useful for testing the display and manually updating it.

Usage:
    # Display the default image (inky_ready.png)
    python3 display_inky.py
    
    # Display a specific image
    python3 display_inky.py --image my_image.png
    
    # Display with verbose output
    python3 display_inky.py --verbose
"""

import sys
import os
import argparse

# Try to import Inky display library
try:
    from inky.auto import auto
    HAS_INKY = True
except ImportError:
    HAS_INKY = False
    print("Warning: Inky library not found. Install with: pip install inky[rpi,fonts]")

# Try to import PIL/Pillow
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL/Pillow not found. Install with: pip install pillow")


def display_image_on_inky(image_path, verbose=False):
    """
    Display an image on the Inky Impression 7.3" display
    
    Args:
        image_path: Path to the image file to display
        verbose: If True, print detailed information
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not HAS_INKY:
        print("Error: Inky library not available.")
        print("Install it with: pip install inky[rpi,fonts]")
        return False
    
    if not HAS_PIL:
        print("Error: PIL/Pillow required for image loading.")
        print("Install it with: pip install pillow")
        return False
    
    # Check if image file exists
    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}")
        return False
    
    try:
        if verbose:
            print(f"Loading image: {image_path}")
        
        # Load the image
        img = Image.open(image_path)
        if verbose:
            print(f"Image loaded: {img.size} pixels, mode: {img.mode}")
        
        # Initialize Inky display (auto-detects the connected display)
        if verbose:
            print("Initializing Inky display...")
        try:
            inky = auto()
        except Exception as init_error:
            error_msg = str(init_error)
            if "CS0" in error_msg or "chip select" in error_msg.lower() or "GPIO8" in error_msg:
                print("\n" + "=" * 60)
                print("ERROR: SPI Chip Select Conflict Detected")
                print("=" * 60)
                print("\nThe Inky display cannot access GPIO8 (CS0) because it's")
                print("already claimed by the hardware SPI interface.")
                print("\nSOLUTION: Add the following line to /boot/firmware/config.txt:")
                print("  dtoverlay=spi0-0cs")
                print("\nThen reboot your Raspberry Pi:")
                print("  sudo reboot")
                print("\nThis disables hardware CS management and lets the Inky")
                print("library control the chip select pin in software.")
                print("=" * 60)
                return False
            else:
                # Re-raise if it's a different error
                raise
        
        if verbose:
            print(f"Inky display detected: {inky.__class__.__name__}")
            print(f"Display resolution: {inky.resolution}")
            # Check if colours attribute exists (it might be 'colour' instead)
            if hasattr(inky, 'colours'):
                print(f"Display colors: {inky.colours}")
            elif hasattr(inky, 'colour'):
                print(f"Display color: {inky.colour}")
        
        # Resize image to match display resolution if needed
        if img.size != inky.resolution:
            if verbose:
                print(f"Resizing image from {img.size} to {inky.resolution}...")
            # Use LANCZOS resampling for best quality
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            img = img.resize(inky.resolution, resample)
            if verbose:
                print(f"Image resized to: {img.size}")
        
        # Ensure image is in RGB mode (Inky expects RGB)
        if img.mode != 'RGB':
            if verbose:
                print(f"Converting image from {img.mode} to RGB...")
            img = img.convert('RGB')
        
        # Set the image on the display
        if verbose:
            print("Setting image on display...")
        inky.set_image(img)
        inky.set_border(inky.WHITE)
        
        # Update the display
        if verbose:
            print("Updating display (this may take a few seconds)...")
        inky.show()
        
        print("✓ Display updated successfully!")
        if verbose:
            print(f"  Image: {image_path}")
            print(f"  Display: {inky.__class__.__name__}")
            print(f"  Resolution: {inky.resolution}")
        
        return True
        
    except Exception as e:
        print(f"Error displaying on Inky: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Display an image on the Inky Impression 7.3" display',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 display_inky.py
  python3 display_inky.py --image my_image.png
  python3 display_inky.py --image inky_ready.png --verbose
        """
    )
    parser.add_argument(
        '--image', '-i',
        default='inky_ready.png',
        help='Path to image file to display (default: inky_ready.png)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed information'
    )
    
    args = parser.parse_args()
    
    # Print diagnostic information
    print("Inky Display Tool")
    print("=" * 50)
    print(f"Image file: {args.image}")
    print(f"Inky library: {'✓ Available' if HAS_INKY else '✗ Missing'}")
    print(f"PIL/Pillow: {'✓ Available' if HAS_PIL else '✗ Missing'}")
    print()
    
    # Display the image
    success = display_image_on_inky(args.image, verbose=args.verbose)
    
    if success:
        return 0
    else:
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

