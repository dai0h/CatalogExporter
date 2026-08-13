import sys

from diskmenu.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        from diskmenu.entry import start_gui

        start_gui()
    elif len(sys.argv) == 2 and sys.argv[1] in ("--autostart", "--tray"):
        from diskmenu.entry import start_tray

        start_tray()
    else:
        raise SystemExit(main())
