# -*- coding: utf-8 -*-
"""Prompt Vault 图库接口：图库源管理、图片列表、缩略图、提示词预览。

注意：ComfyUI 的动态自定义路由只稳定支持 GET，因此所有有副作用的接口
（添加 / 移除图库、选择文件夹）都走 GET + query 参数；图片导入直接复用
官方 /upload/image。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

try:
    from aiohttp import web
    import folder_paths
    from server import PromptServer
except Exception:  # 独立脚本里 import 本包时没有这些依赖
    PromptServer = None

from .prompt_vault import IMAGE_EXTS, read_prompt

_SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_SCAN = 20000
_MAX_FILES = 60000
_THUMB_SIZE = 1024


def _lib_dir() -> Path:
    path = Path(folder_paths.get_user_directory()) / "prompt_vault"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _thumb_dir() -> Path:
    path = _lib_dir() / "thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _library_dir() -> Path:
    """“我的图库”目录，同时也是官方上传接口的落点。"""
    path = Path(folder_paths.get_input_directory()) / "prompt_vault"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sources_file() -> Path:
    return _lib_dir() / "sources.json"


def _write_json(path: Path, data) -> None:
    with tempfile.NamedTemporaryFile(dir=str(path.parent), suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _custom_sources() -> list[dict]:
    path = _sources_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or "")
        folder = str(item.get("path") or "")
        if not source_id.startswith("custom_") or not folder:
            continue
        rows.append({
            "id": source_id,
            "name": str(item.get("name") or Path(folder).name or folder),
            "path": folder,
            "removable": True,
        })
    return rows


def _all_sources() -> list[dict]:
    sources = [
        {"id": "output", "name": "output", "removable": False,
         "path": str(folder_paths.get_output_directory())},
    ]
    return sources + _custom_sources()


def _find_source(source_id: str) -> dict | None:
    return next((source for source in _all_sources() if source["id"] == source_id), None)


def _allowed_roots() -> list[Path]:
    roots = []
    for source in _all_sources():
        try:
            roots.append(Path(source["path"]).resolve())
        except OSError:
            continue
    # 拖入 / 导入时的暂存目录，不显示为图库但允许预览和读取
    try:
        roots.append(_library_dir().resolve())
    except OSError:
        pass
    return roots


def _is_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(resolved.is_relative_to(root) for root in _allowed_roots())


_SIZE_CACHE: dict[str, tuple[float, int, int]] = {}


def _image_size(path: Path, modified: float) -> tuple[int, int]:
    key = str(path)
    hit = _SIZE_CACHE.get(key)
    if hit and hit[0] == modified:
        return hit[1], hit[2]
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        width, height = 0, 0
    if len(_SIZE_CACHE) > 8000:
        _SIZE_CACHE.clear()
    _SIZE_CACHE[key] = (modified, width, height)
    return width, height


def _list_sync(source_id: str, folder: str, query: str, offset: int, limit: int) -> dict:
    source = _find_source(source_id)
    if source is None:
        raise ValueError("图库不存在")
    root = Path(source["path"]).resolve()
    if not root.is_dir():
        return {"items": [], "total": 0}

    folder = str(folder or "").strip().strip("/").replace("\\", "/")
    scan_root = root
    if folder:
        candidate = (root / folder).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_dir():
            raise ValueError("文件夹不存在")
        scan_root = candidate

    query = (query or "").strip().lower()
    rows: list[tuple[float, str, Path, int]] = []
    scanned = 0
    for dir_path, dir_names, file_names in os.walk(scan_root):
        dir_names[:] = [name for name in dir_names if not name.startswith(".") and name != "thumbs"]
        for file_name in file_names:
            scanned += 1
            if scanned > _MAX_FILES:
                break
            if Path(file_name).suffix.lower() not in IMAGE_EXTS:
                continue
            path = Path(dir_path) / file_name
            try:
                stat = path.stat()
            except OSError:
                continue
            relative = path.relative_to(root).as_posix()
            if query and query not in relative.lower():
                continue
            rows.append((stat.st_mtime, relative, path, stat.st_size))
            if len(rows) >= _MAX_SCAN:
                break
        if scanned > _MAX_FILES or len(rows) >= _MAX_SCAN:
            break

    rows.sort(key=lambda item: item[0], reverse=True)
    total = len(rows)
    items = []
    for modified, relative, path, size in rows[offset:offset + limit]:
        width, height = _image_size(path, modified)
        items.append({
            "path": str(path),
            "name": path.name,
            "rel": relative,
            "mtime": modified,
            "size": size,
            "width": width,
            "height": height,
            "has_prompt": path.with_suffix(".txt").is_file() or path.with_suffix(".json").is_file(),
        })
    return {"items": items, "total": total}


def _tree_sync(source_id: str) -> dict:
    source = _find_source(source_id)
    if source is None:
        raise ValueError("图库不存在")
    root = Path(source["path"])
    if not root.is_dir():
        return {"total": 0, "folders": []}

    budget = {"count": 0}

    def walk(folder: Path, relative: str, depth: int):
        total = 0
        children = []
        dirs = []
        if budget["count"] > 3000:
            return 0, []
        budget["count"] += 1
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.startswith(".") or entry.name == "thumbs":
                            continue
                        dirs.append(entry)
                    elif Path(entry.name).suffix.lower() in IMAGE_EXTS:
                        total += 1
        except OSError:
            return 0, []
        dirs.sort(key=lambda entry: entry.name.lower())
        for entry in dirs:
            child_relative = f"{relative}/{entry.name}" if relative else entry.name
            child_total, child_children = walk(Path(entry.path), child_relative, depth + 1)
            total += child_total
            if depth < 5:
                children.append({
                    "path": child_relative,
                    "name": entry.name,
                    "count": child_total,
                    "children": child_children,
                })
        return total, children

    total, folders = walk(root, "", 0)
    return {"total": total, "folders": folders}


def _forest_sync() -> dict:
    """所有图库源 + 各自的子文件夹树，供左侧栏一次渲染。"""
    rows = []
    for source in _all_sources():
        try:
            tree = _tree_sync(source["id"])
        except (ValueError, OSError):
            tree = {"total": 0, "folders": []}
        rows.append({**source, "total": tree["total"], "folders": tree["folders"]})
    return {"sources": rows}


def _thumb_sync(raw_path: str) -> Path:
    from PIL import Image, ImageOps

    path = Path(raw_path)
    if not path.is_file() or not _is_allowed(path):
        raise FileNotFoundError("图片不存在或不在图库范围内")

    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()
    target = _thumb_dir() / f"{digest}_{_THUMB_SIZE}.webp"
    try:
        if target.is_file() and target.stat().st_mtime >= path.stat().st_mtime:
            return target
    except OSError:
        pass

    with Image.open(path) as source:
        source.draft("RGB", (_THUMB_SIZE * 2, _THUMB_SIZE * 2))
        image = ImageOps.exif_transpose(source)
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            image = image.convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, image).convert("RGB")
        else:
            image = image.convert("RGB")
        image.thumbnail((_THUMB_SIZE, _THUMB_SIZE))

    with tempfile.NamedTemporaryFile(dir=str(target.parent), suffix=".webp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        image.save(temporary, "WEBP", quality=85)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _import_sync(name: str, dest: str) -> str:
    """把官方上传到 input/prompt_vault 的图片移动到指定图库文件夹。"""
    filename = Path(str(name or "")).name
    if not filename:
        raise ValueError("缺少文件名")
    source = _library_dir() / filename
    if not source.is_file():
        raise FileNotFoundError("暂存文件不存在")

    folder = Path(str(dest or "")).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise ValueError("目标文件夹不存在")
    if not _is_allowed(folder):
        raise ValueError("目标文件夹不在图库范围内")
    if source.parent.resolve() == folder.resolve():
        return str(source)

    target = folder / source.name
    index = 2
    while target.exists():
        target = folder / f"{source.stem}_{index}{source.suffix}"
        index += 1
    shutil.move(str(source), str(target))
    for suffix in (".txt", ".json"):
        side = source.with_suffix(suffix)
        if side.is_file():
            shutil.move(str(side), str(target.with_suffix(suffix)))
    return str(target)


def _pick_directory_sync(initial: str = "") -> str:
    start = str(initial or "").strip()
    if not start or not Path(start).is_dir():
        start = str(folder_paths.get_output_directory())

    # Windows：用系统原生文件夹选择框，避免依赖 tkinter
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        powershell = os.path.join(
            system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
        )
        if not os.path.isfile(powershell):
            powershell = "powershell.exe"
        script = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.Description = '选择图库文件夹'; "
            "$d.ShowNewFolderButton = $true; "
            "$d.SelectedPath = $env:PV_INITIAL; "
            "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
            "{ [Console]::Out.Write($d.SelectedPath) }"
        )
        env = os.environ.copy()
        env["PV_INITIAL"] = start
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-STA", "-Command", script],
                capture_output=True, timeout=600, env=env, creationflags=creation,
            )
        except Exception as exc:
            print(f"[liyue-tools-comfy] 文件夹选择框调用失败：{exc}")
            raise RuntimeError(f"文件夹选择框调用失败：{exc}") from exc
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", "ignore").strip()
            print(f"[liyue-tools-comfy] 文件夹选择框返回错误：{message}")
            raise RuntimeError(message or "文件夹选择框启动失败")
        return result.stdout.decode("utf-8", "ignore").strip()

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError(f"当前系统没有可用的文件夹选择框：{exc}") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        path = filedialog.askdirectory(parent=root, initialdir=start, title="选择图库文件夹", mustexist=True)
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    return str(path or "")


def interactively_add_source(folder: Path, name: str = "") -> dict:
    """添加一个图库目录并返回新条目。"""
    if not folder.is_absolute() or not folder.is_dir():
        raise ValueError("请选择有效的绝对文件夹路径")
    if any(str(folder).lower() == source["path"].lower() for source in _all_sources()):
        raise ValueError("该文件夹已在图库中")

    custom = _custom_sources()
    entry = {
        "id": "custom_" + uuid.uuid4().hex[:8],
        "name": _SAFE_NAME_RE.sub("_", str(name or "").strip()) or folder.name or str(folder),
        "path": str(folder),
    }
    custom.append(entry)
    _write_json(_sources_file(), custom)
    return entry


def register_routes():
    if PromptServer is None or getattr(PromptServer, "instance", None) is None:
        return
    routes = PromptServer.instance.routes

    @routes.get("/prompt_vault/sources")
    async def sources_get(request):
        return web.json_response({"sources": _all_sources()}, headers={"Cache-Control": "no-store"})

    @routes.get("/prompt_vault/source_add")
    async def source_add(request):
        raw = str(request.query.get("path") or "").strip()
        name = str(request.query.get("name") or "")
        try:
            entry = interactively_add_source(Path(raw).expanduser(), name)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except OSError as exc:
            return web.json_response({"error": str(exc)}, status=500)
        entry["removable"] = True
        return web.json_response({"source": entry, "sources": _all_sources()})

    @routes.get("/prompt_vault/source_add_staged")
    async def source_add_staged(request):
        raw = str(request.query.get("name") or "").strip()
        name = _SAFE_NAME_RE.sub("_", raw).strip(" .")
        if not name:
            return web.json_response({"error": "缺少文件夹名"}, status=400)

        folder = _library_dir() / name
        folder.mkdir(parents=True, exist_ok=True)

        existing = next(
            (source for source in _all_sources()
             if Path(source["path"]).resolve() == folder.resolve()),
            None,
        )
        if existing:
            return web.json_response({"source": existing, "sources": _all_sources()})

        try:
            entry = interactively_add_source(folder, name)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        link = {"id": entry["id"], "name": entry["name"],
                "path": entry["path"], "removable": True}
        return web.json_response({"source": link, "sources": _all_sources()})

    @routes.get("/prompt_vault/source_remove")
    async def source_remove(request):
        source_id = str(request.query.get("id") or "")
        custom = _custom_sources()
        remaining = [source for source in custom if source["id"] != source_id]
        if len(remaining) == len(custom):
            return web.json_response({"error": "只能移除自己添加的图库"}, status=400)
        _write_json(_sources_file(), remaining)
        return web.json_response({"sources": _all_sources()})

    @routes.get("/prompt_vault/items")
    async def items_get(request):
        source_id = str(request.query.get("source") or "output")
        folder = str(request.query.get("folder") or "")
        query = str(request.query.get("q") or "")
        try:
            offset = max(0, int(request.query.get("offset", 0) or 0))
            limit = min(120, max(1, int(request.query.get("limit", 60) or 60)))
        except ValueError:
            return web.json_response({"error": "分页参数错误"}, status=400)
        try:
            payload = await asyncio.to_thread(_list_sync, source_id, folder, query, offset, limit)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except OSError as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response(payload, headers={"Cache-Control": "no-store"})

    @routes.get("/prompt_vault/tree")
    async def tree_get(request):
        source_id = str(request.query.get("source") or "output")
        try:
            payload = await asyncio.to_thread(_tree_sync, source_id)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except OSError as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response(payload, headers={"Cache-Control": "no-store"})

    @routes.get("/prompt_vault/forest")
    async def forest_get(request):
        try:
            payload = await asyncio.to_thread(_forest_sync)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response(payload, headers={"Cache-Control": "no-store"})

    @routes.get("/prompt_vault/thumb")
    async def thumb_get(request):
        raw = str(request.query.get("path") or "")
        try:
            path = await asyncio.to_thread(_thumb_sync, raw)
        except FileNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except Exception as exc:
            return web.json_response({"error": f"缩略图生成失败：{exc}"}, status=500)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})

    @routes.get("/prompt_vault/file")
    async def file_get(request):
        path = Path(str(request.query.get("path") or ""))
        if not path.is_file() or not _is_allowed(path):
            return web.json_response({"error": "图片不存在或不在图库范围内"}, status=404)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})

    @routes.get("/prompt_vault/prompt")
    async def prompt_get(request):
        path = Path(str(request.query.get("path") or ""))
        if not path.is_file() or not _is_allowed(path):
            return web.json_response({"error": "图片不存在或不在图库范围内"}, status=404)
        try:
            info = await asyncio.to_thread(read_prompt, path)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({
            "positive": info["positive"],
            "negative": info["negative"],
            "loras": info["loras"],
            "checkpoint": info["checkpoint"],
            "seed": info["seed"],
            "source": info["source"],
        }, headers={"Cache-Control": "no-store"})

    @routes.get("/prompt_vault/import")
    async def import_image(request):
        name = str(request.query.get("name") or "")
        dest = str(request.query.get("dest") or "")
        try:
            path = await asyncio.to_thread(_import_sync, name, dest)
        except FileNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except OSError as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"path": path})

    @routes.get("/prompt_vault/delete")
    async def delete_image(request):
        path = Path(str(request.query.get("path") or ""))
        if not path.is_file() or not _is_allowed(path):
            return web.json_response({"error": "文件不存在或不在图库范围内"}, status=404)
        try:
            path.unlink()
            for suffix in (".txt", ".json"):
                side = path.with_suffix(suffix)
                if side.is_file():
                    side.unlink()
        except OSError as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"success": True})

    @routes.get("/prompt_vault/stage_path")
    async def stage_path(request):
        name = Path(str(request.query.get("name") or "")).name
        if not name:
            return web.json_response({"error": "缺少文件名"}, status=400)
        path = _library_dir() / name
        if not path.is_file():
            return web.json_response({"error": "文件不存在"}, status=404)
        return web.json_response({"path": str(path)})

    @routes.get("/prompt_vault/pick_dir")
    async def pick_dir(request):
        initial = str(request.query.get("initial") or "")
        try:
            path = await asyncio.to_thread(_pick_directory_sync, initial)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"path": path})


try:
    register_routes()
except Exception:
    pass
