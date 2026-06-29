import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from linux_maa.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["update-game"]))
