#!/usr/bin/env python3
"""MMI3G-Toolkit - root launcher for the desktop GUI.

Convenience entry point so the GUI can be started from the repository root:

    python mmi3g_toolkit.py

It simply loads builder/gui.py and runs it. The real code lives in builder/.
"""

import os
import sys

BUILDER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "builder")
if BUILDER_DIR not in sys.path:
    sys.path.insert(0, BUILDER_DIR)

from gui import main  # noqa: E402  (path tweaked above)

if __name__ == "__main__":
    main()
