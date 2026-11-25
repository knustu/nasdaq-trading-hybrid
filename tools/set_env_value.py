from __future__ import annotations

import sys
from pathlib import Path


def set_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            if not replaced:
                updated.append(f"{key}={value}")
                replaced = True
            continue
        updated.append(line)
    if not replaced:
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(f"{key}={value}")
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: set_env_value.py PATH KEY VALUE")
    set_value(Path(sys.argv[1]), sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
