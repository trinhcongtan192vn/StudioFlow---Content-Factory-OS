"""Đọc/ghi file JSON trên workspace + version hoá — specs/01 mục 5, §02 mục 4.

Version = ghi file mới `*.v{n}.json` + thêm dòng bảng version + cập nhật con trỏ hiện hành.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_versioned(dir_path: Path, base_name: str, data: dict, version: int) -> tuple[Path, Path]:
    """Ghi bản hiện hành `<base_name>.json` + snapshot `<base_name>.v{n}.json`.
    Trả (current_path, version_path)."""
    current = dir_path / f"{base_name}.json"
    versioned = dir_path / f"{base_name}.v{version}.json"
    write_json(current, data)
    write_json(versioned, data)
    return current, versioned
