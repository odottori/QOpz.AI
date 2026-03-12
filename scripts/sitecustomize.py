from __future__ import annotations

import os
import tempfile


if os.name == "nt":
    _orig_mkdtemp = tempfile.mkdtemp

    def _patched_mkdtemp(suffix=None, prefix=None, dir=None):
        orig_mkdir = os.mkdir

        def _mkdir_win(path, mode=0o777, *args, **kwargs):
            if mode == 0o700:
                mode = 0o777
            return orig_mkdir(path, mode, *args, **kwargs)

        os.mkdir = _mkdir_win
        try:
            return _orig_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        finally:
            os.mkdir = orig_mkdir

    tempfile.mkdtemp = _patched_mkdtemp
