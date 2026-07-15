"""Development uvicorn launcher for Windows-friendly reload."""

from __future__ import annotations

import argparse
import sys
from typing import Any

import uvicorn


def _patch_windows_reload() -> None:
    if sys.platform != "win32":
        return

    from uvicorn import _subprocess
    from uvicorn.supervisors import basereload

    def restart(self: Any) -> None:
        self.process.terminate()
        self.process.join()
        self.process = _subprocess.get_subprocess(
            config=self.config,
            target=self.target,
            sockets=self.sockets,
        )
        self.process.start()

    basereload.BaseReload.restart = restart


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Lore Chat development API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload-dir", action="append", dest="reload_dirs", default=[])
    args = parser.parse_args(argv)

    _patch_windows_reload()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=True,
        reload_dirs=args.reload_dirs or None,
        log_config="uvicorn_log.json",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
