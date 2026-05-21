# PyInstaller runtime hook: add bundle dir to PATH so fpcalc(.exe) is found
import os
import sys

if sys.platform == "win32" and getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")
