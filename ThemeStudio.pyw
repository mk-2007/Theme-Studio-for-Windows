# Double-click to start Theme Studio without a console window.
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import main  # noqa: E402

sys.exit(main.main())
