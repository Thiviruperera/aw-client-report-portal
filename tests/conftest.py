"""Pytest config — opts out of import-time DB setup in app.py."""
import os

os.environ["SKIP_AUTOSEED"] = "1"
