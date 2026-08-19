"""按 assets.json 白名单下载、转换并校验本地界面图片。"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_DIR / "data" / "assets.json"
ASSET_ROOT = PROJECT_DIR / "assets"


class AssetError(ValueError):
    """资源清单或图片文件不符合约定。"""


def load_manifest() -> dict[str, object]:
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetError(f"无法读取资源清单：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("assets"), dict):
        raise AssetError("assets.json 缺少 assets 对象")
    return data


def destination_for(entry: dict[str, object]) -> Path:
    raw_path = entry.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise AssetError("资源路径必须是非空字符串")
    destination = (PROJECT_DIR / raw_path).resolve()
    if ASSET_ROOT.resolve() not in destination.parents:
        raise AssetError(f"资源路径越界：{raw_path}")
    return destination


def expected_size(entry: dict[str, object]) -> tuple[int, int]:
    raw_size = entry.get("size")
    if (
        not isinstance(raw_size, list)
        or len(raw_size) != 2
        or not all(isinstance(value, int) and value > 0 for value in raw_size)
    ):
        raise AssetError(f"资源尺寸无效：{raw_size}")
    return raw_size[0], raw_size[1]


def normalized_image(payload: bytes, size: tuple[int, int]) -> Image.Image:
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            image = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise AssetError(f"无法解码图片：{exc}") from exc
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    left = (size[0] - image.width) // 2
    top = (size[1] - image.height) // 2
    canvas.alpha_composite(image, (left, top))
    return canvas


def valid_local_file(path: Path, size: tuple[int, int]) -> bool:
    try:
        with Image.open(path) as image:
            image.load()
            return image.format == "PNG" and image.size == size
    except (OSError, ValueError):
        return False


def download(entry: dict[str, object]) -> bytes:
    url = entry.get("source_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise AssetError(f"只允许 HTTPS 资源地址：{url}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "WuwaPlannerAssetSync/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise AssetError(f"下载失败 {url}：{exc}") from exc


def validate_manifest(manifest: dict[str, object]) -> list[str]:
    assets = manifest["assets"]
    assert isinstance(assets, dict)
    errors: list[str] = []
    seen_paths: set[Path] = set()
    for key, raw_entry in assets.items():
        try:
            if not isinstance(key, str) or not key:
                raise AssetError("资源键必须是非空字符串")
            if not isinstance(raw_entry, dict):
                raise AssetError(f"{key} 的资源定义必须是对象")
            _ = expected_size(raw_entry)
            path = destination_for(raw_entry)
            if path in seen_paths:
                raise AssetError(f"资源目标路径重复：{path}")
            seen_paths.add(path)
            category = raw_entry.get("category")
            if category not in {"character", "material", "echo"}:
                raise AssetError(f"{key} 的类别无效：{category}")
            if not str(raw_entry.get("source_url", "")).startswith("https://"):
                raise AssetError(f"{key} 缺少 HTTPS 原始地址")
        except AssetError as exc:
            errors.append(str(exc))
    return errors


def sync(manifest: dict[str, object], check_only: bool) -> int:
    manifest_errors = validate_manifest(manifest)
    if manifest_errors:
        for error in manifest_errors:
            print(f"清单错误：{error}", file=sys.stderr)
        return 1

    assets = manifest["assets"]
    assert isinstance(assets, dict)
    completed = skipped = failed = 0
    for key, raw_entry in assets.items():
        assert isinstance(raw_entry, dict)
        destination = destination_for(raw_entry)
        size = expected_size(raw_entry)
        if valid_local_file(destination, size):
            skipped += 1
            continue
        if check_only:
            print(f"资源缺失或尺寸错误：{key} -> {destination}", file=sys.stderr)
            failed += 1
            continue
        try:
            payload = download(raw_entry)
            image = normalized_image(payload, size)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".tmp.png")
            image.save(temporary, format="PNG", optimize=True)
            temporary.replace(destination)
            completed += 1
            print(f"已同步：{key}")
        except (AssetError, OSError) as exc:
            failed += 1
            print(f"资源失败：{key}：{exc}", file=sys.stderr)

    action = "校验" if check_only else "同步"
    print(f"资源{action}完成：新增 {completed}，已存在 {skipped}，失败 {failed}。")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步鸣潮助手本地图片资源")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download", action="store_true", help="下载并转换缺失资源")
    group.add_argument("--check", action="store_true", help="只校验清单和本地文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = load_manifest()
    except AssetError as exc:
        print(f"资源清单错误：{exc}", file=sys.stderr)
        return 1
    return sync(manifest, check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
