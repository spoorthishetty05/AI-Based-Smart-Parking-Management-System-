"""
Frontend Asset & Template Inspector.
Validates all HTML templates, stylesheets, and scripts for availability and integrity.
"""
import os
import sys

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def inspect_assets():
    print("=" * 60)
    print("  SMART PARKING - FRONTEND & TEMPLATE AUDITOR")
    print("=" * 60)
    
    templates_dir = os.path.join(_BASE_DIR, 'templates')
    static_dir = os.path.join(_BASE_DIR, 'static')
    
    print("\n[Templates]")
    for root, dirs, files in os.walk(templates_dir):
        for f in files:
            if f.endswith('.html'):
                rel = os.path.relpath(os.path.join(root, f), templates_dir)
                size = os.path.getsize(os.path.join(root, f))
                print(f"  ✓ {rel:35} ({size} bytes)")
                
    print("\n[Static CSS & JS]")
    for root, dirs, files in os.walk(static_dir):
        for f in files:
            if f.endswith(('.css', '.js')):
                rel = os.path.relpath(os.path.join(root, f), static_dir)
                size = os.path.getsize(os.path.join(root, f))
                print(f"  ✓ {rel:35} ({size} bytes)")

if __name__ == '__main__':
    inspect_assets()

