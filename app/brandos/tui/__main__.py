"""
Enables `python -m brandos.tui` to run the app directly, rather than
needing `python -m brandos.tui.app`.
"""
from brandos.tui.app import DigestApp

if __name__ == "__main__":
    DigestApp().run()
