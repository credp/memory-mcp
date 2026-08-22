from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    if "Username" in prompt:
        print("x-access-token")
        return
    if "Password" not in prompt:
        raise SystemExit(1)
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise SystemExit("CREDENTIALS_DIRECTORY is not configured")
    credential = Path(directory) / "github_pat"
    token = credential.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("GitHub credential is empty")
    print(token)


if __name__ == "__main__":
    main()
