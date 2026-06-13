"""
PyInstaller entry point.
Run directly:  python main.py
Frozen:        ./iphone-manager  (Mac)  or  iphone-manager.exe  (Windows)
"""
from iphone_manager.app import main

if __name__ == '__main__':
    main()
