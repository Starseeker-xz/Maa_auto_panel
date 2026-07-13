from __future__ import annotations

import os
import time

from maa_auto_panel.maa.cleanup import MaaDebugRetentionPolicy, enforce_maa_debug_retention
from maa_auto_panel.maa.runtime import MaaRuntime


def test_maa_debug_retention_rotates_asst_log_and_prunes_owned_debug_files(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    debug_dir = runtime.state_home / "maa" / "debug"
    debug_dir.mkdir(parents=True)
    asst_log = debug_dir / "asst.log"
    old_log = debug_dir / "old.log"
    new_log = debug_dir / "new.log"
    asst_log.write_bytes(b"oversized")
    old_log.write_text("old", encoding="utf-8")
    new_log.write_text("new", encoding="utf-8")
    now = time.time()
    os.utime(old_log, (now - 10, now - 10))
    os.utime(new_log, (now, now))

    enforce_maa_debug_retention(
        runtime.layout.maa,
        MaaDebugRetentionPolicy(max_age_days=9999, max_debug_files=2, max_asst_log_bytes=1),
    )

    assert asst_log.read_bytes() == b""
    rotated = list(debug_dir.glob("asst-*.log"))
    assert len(rotated) == 1
    assert rotated[0].read_bytes() == b"oversized"
    assert not old_log.exists()
    assert new_log.exists()
