import sys
import os

# Add SwitchModStudio directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app_window import SwitchModStudioApp

def main():
    app = SwitchModStudioApp()
    app.mainloop()

if __name__ == "__main__":
    main()
