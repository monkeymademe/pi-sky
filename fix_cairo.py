#!/usr/bin/env python3
"""
Fix cairocffi to find Cairo library on macOS with Homebrew
This patches cairocffi's __init__.py to check Homebrew paths
"""
import os
import sys
import shutil

def fix_cairocffi():
    """Patch cairocffi to find Homebrew Cairo on macOS"""
    # Find cairocffi location without importing it
    import site
    site_packages = site.getsitepackages()
    if not site_packages:
        site_packages = [site.USER_SITE] if site.USER_SITE else []
    
    cairocffi_init = None
    for sp in site_packages:
        candidate = os.path.join(sp, 'cairocffi', '__init__.py')
        if os.path.exists(candidate):
            cairocffi_init = candidate
            break
    
    # Also check user site
    if not cairocffi_init and site.USER_SITE:
        candidate = os.path.join(site.USER_SITE, 'cairocffi', '__init__.py')
        if os.path.exists(candidate):
            cairocffi_init = candidate
    
    if not cairocffi_init:
        # Try common location
        common_path = '/Users/jamesmitchell/Library/Python/3.9/lib/python/site-packages/cairocffi/__init__.py'
        if os.path.exists(common_path):
            cairocffi_init = common_path
    
    if not cairocffi_init:
        print("Error: Could not find cairocffi __init__.py file")
        print("  Searched in:", site_packages)
        return False
    
    print(f"Found cairocffi at: {cairocffi_init}")
    
    # Read current source
    with open(cairocffi_init, 'r') as f:
        source = f.read()
    
    # Check if already patched
    if '# Patched for Homebrew' in source:
        print("✓ cairocffi is already patched for Homebrew")
        return True
    
    # Create backup
    backup = cairocffi_init + '.backup'
    if not os.path.exists(backup):
        shutil.copy(cairocffi_init, backup)
        print(f"Created backup: {backup}")
    
    # Patch the dlopen function to check Homebrew before raising error
    homebrew_check = '''    # Patched for Homebrew Cairo support on macOS
    if sys.platform == 'darwin':
        homebrew_paths = ['/opt/homebrew/lib/libcairo.2.dylib', '/usr/local/lib/libcairo.2.dylib']
        for homebrew_cairo in homebrew_paths:
            if os.path.exists(homebrew_cairo):
                try:
                    return ffi.dlopen(homebrew_cairo)
                except OSError:
                    pass
    
'''
    
    # Insert before the final OSError raise in dlopen function
    if 'raise OSError(error_message)' in source:
        # Find the exact location - it should be in the dlopen function
        source = source.replace(
            '    error_message = \'\\n\'.join(  # pragma: no cover\n        str(exception) for exception in exceptions)\n    raise OSError(error_message)  # pragma: no cover',
            homebrew_check + '    error_message = \'\\n\'.join(  # pragma: no cover\n        str(exception) for exception in exceptions)\n    raise OSError(error_message)  # pragma: no cover'
        )
        
        # Write patched version
        with open(cairocffi_init, 'w') as f:
            f.write(source)
        
        print("✓ Successfully patched cairocffi for Homebrew Cairo")
        print("  The patch adds Homebrew library path checking before raising errors")
        return True
    else:
        print("Could not find OSError raise statement to patch")
        return False

if __name__ == '__main__':
    if fix_cairocffi():
        print("\nNow try running map_to_svg.py again!")
    else:
        print("\nPatch failed - you may need to use the wrapper script instead")

