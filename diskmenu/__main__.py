import sys

from .cli import main

if len(sys.argv) == 1:
    from .entry import start_gui

    start_gui()
elif len(sys.argv) == 2 and sys.argv[1] in ("--autostart", "--tray"):
    from .entry import start_tray

    start_tray()
else:
    raise SystemExit(main())
