"""后台托盘模式入口（无窗口）。"""

import os
import sys
import traceback


def _main() -> None:
    from diskmenu.entry import start_tray

    start_tray()


if __name__ == "__main__":
    try:
        _main()
    except Exception:
        log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DiskMenu")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "error.log"), "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise

