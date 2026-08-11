from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_project_version_matches_release_tag() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    tag = os.environ.get("RELEASE_TAG")
    if tag is None:
        tags = subprocess.run(
            ["git", "tag", "--points-at", "HEAD", "--list", "v*"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.splitlines()
        if not tags:
            pytest.skip("HEAD is not a tagged release")
        assert len(tags) == 1, f"expected one release tag at HEAD, found: {tags}"
        tag = tags[0]

    assert tag == f"v{version}"
