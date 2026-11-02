"""
Operational, Database Seeding, and Administrative Scripts Package.
"""

import os
import sys

# Ensure root and core are in sys.path for all scripts
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPTS_DIR)
for _p in [_ROOT_DIR, os.path.join(_ROOT_DIR, 'core')]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

