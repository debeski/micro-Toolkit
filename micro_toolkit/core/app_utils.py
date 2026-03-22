from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path


def open_file_or_folder(path: str | os.PathLike[str]) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return True
    except Exception as exc:
        print(f"Error opening {target}: {exc}")
        return False


def generate_output_filename(operation: str, source_name: str, extension: str = ".xlsx") -> str:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(char for char in source_name if char.isalnum() or char in (" ", ".", "_", "-")).strip()
    fallback_name = safe_name or "output"
    return f"{operation}_{fallback_name}_{timestamp}{extension}"
