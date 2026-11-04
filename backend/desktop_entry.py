"""Desktop / frozen entry point for the SinyalAbidnet Kliper Pro backend.

This module is only used by the PyInstaller-built executable bundled with the
Electron desktop app. It adds a thin compatibility layer so the existing
backend code keeps working when ``sys.executable`` is no longer a real Python
interpreter:

* ``--run-module <module> [args...]`` re-enters this executable to run a bundled
  Python CLI module (used for ``yt-dlp`` / ``youtube_transcript_api`` subprocesses).
* Child processes spawned on Windows are created with ``CREATE_NO_WINDOW`` so no
  black console windows flash while rendering videos.
* The FastAPI app is served with uvicorn on the host/port provided by the
  Electron shell via the ``HOST`` / ``PORT`` environment variables.
"""

import os
import runpy
import sys


def _run_module_from_args(argv) -> bool:
    """If invoked as ``--run-module <module> ...``, execute that module and return True."""
    if "--run-module" not in argv:
        return False
    marker = argv.index("--run-module")
    if marker + 1 >= len(argv):
        raise SystemExit("--run-module requires a module name")
    module = argv[marker + 1]
    sys.argv = [module, *argv[marker + 2:]]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return True


def _hide_child_console_windows() -> None:
    """Make every subprocess.Popen on Windows run without popping a console window."""
    if os.name != "nt":
        return
    import subprocess

    original_init = subprocess.Popen.__init__

    def patched_init(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        original_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = patched_init


def main() -> None:
    # Subprocess helper mode: `backend.exe --run-module yt_dlp ...`
    if _run_module_from_args(sys.argv):
        return

    _hide_child_console_windows()

    # Ensure the project root is importable (harmless in frozen builds, required if run as script).
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))

    import uvicorn
    from backend.main import app

    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info"), access_log=False)


if __name__ == "__main__":
    main()
