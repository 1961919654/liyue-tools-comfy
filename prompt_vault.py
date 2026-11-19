# -*- coding: utf-8 -*-
"""Prompt Vault：保存图片时附带同名 txt 提示词；用节点内图库面板选图后自动读取提示词。

节点
----
* PromptVaultSave  保存图片 + 同名 .txt（正向提示词）+ PNG 元数据
* PromptVaultLoad  从图库面板选择图片，输出图片与提示词

图库、缩略图、上传等 HTTP 接口见 routes.py。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageSequence
from PIL.PngImagePlugin import PngInfo

import folder_paths
from comfy.cli_args import args

SCHEMA = "prompt-vault/1"
META_KEY = "prompt_vault"
DEFAULT_PREFIX = "PV"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".avif"}
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SORT_DIGITS_RE = re.compile(r"(\d+)")
LORA_EXTS = (".safetensors", ".pt", ".pth", ".ckpt", ".bin")
LORA_TAG_RE = re.compile(
    r"<lora:([^:>]+):([-+]?\d*\.?\d+)(?::([-+]?\d*\.?\d+))?>",
    re.IGNORECASE,
)
LORA_KEY_RE = re.compile(r"^(?:lora|lora_name|lora名称|LoRA名称)_?(\d+)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 工作流信息提取
# ---------------------------------------------------------------------------
def _node_sort_key(node_id):
    return [int(part) if part.isdigit() else part for part in _SORT_DIGITS_RE.split(str(node_id))]


def _resolve_text(value, prompt: dict, depth: int = 0) -> str:
    """沿着 conditioning 连接回溯到 CLIPTextEncode 的文本。"""
    if isinstance(value, str):
        return value
    if depth > 8 or not isinstance(value, list) or len(value) != 2:
        return ""
    node = prompt.get(str(value[0]))
    if not isinstance(node, dict):
        return ""
    inputs = node.get("inputs") or {}
    class_type = str(node.get("class_type") or "")
    if "CLIPTextEncode" in class_type:
        return _resolve_text(inputs.get("text", ""), prompt, depth + 1)

    # 提示词来自其它节点（MiniMax 导入、PrimitiveString 等）时取它最长的文本字段
    candidates = []
    for key in ("text", "prompt", "value", "positive_prompt", "orinalMessage", "prompt_text"):
        candidate = inputs.get(key)
        if isinstance(candidate, str) and _looks_like_prompt(candidate):
            candidates.append(candidate)
    if candidates:
        return max(candidates, key=len)

    for key in ("text", "conditioning", "positive", "negative", "conditioning_1"):
        if key in inputs:
            text = _resolve_text(inputs[key], prompt, depth + 1)
            if text:
                return text
    return ""


def _sampler_texts(prompt) -> tuple[str, str]:
    """优先按采样器的 positive / negative 连线取文本，失败再退回 CLIPTextEncode 顺序。"""
    if not isinstance(prompt, dict):
        return "", ""
    for node_id in sorted(prompt, key=_node_sort_key):
        node = prompt[node_id]
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "").lower()
        if "ksampler" not in class_type and "sampler" not in class_type:
            continue
        inputs = node.get("inputs") or {}
        positive = _resolve_text(inputs.get("positive"), prompt)
        negative = _resolve_text(inputs.get("negative"), prompt)
        if positive or negative:
            return positive, negative

    texts: list[str] = []
    for node_id in sorted(prompt, key=_node_sort_key):
        node = prompt[node_id]
        if not isinstance(node, dict):
            continue
        if "CLIPTextEncode" not in str(node.get("class_type") or ""):
            continue
        text = _resolve_text((node.get("inputs") or {}).get("text", ""), prompt)
        if text and text not in texts:
            texts.append(text)
    return (texts[0] if texts else ""), (texts[1] if len(texts) > 1 else "")


def _workflow_extras(prompt) -> dict:
    extras = {"checkpoint": "", "seed": None}
    if not isinstance(prompt, dict):
        return extras
    for node_id in sorted(prompt, key=_node_sort_key):
        node = prompt[node_id]
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "").lower()
        inputs = node.get("inputs") or {}
        if not extras["checkpoint"] and "checkpointloader" in class_type:
            name = inputs.get("ckpt_name")
            if isinstance(name, str):
                extras["checkpoint"] = name
        if extras["seed"] is None and ("ksampler" in class_type or "sampler" in class_type):
            for key in ("seed", "noise_seed"):
                value = inputs.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    extras["seed"] = int(value)
                    break
    return extras


# ---------------------------------------------------------------------------
# LoRA 解析（仅用于面板展示，不参与保存）
# ---------------------------------------------------------------------------
def _norm_lora_name(name) -> str:
    return str(name or "").strip().replace("\\", "/").strip("/")


def _looks_like_lora(name) -> bool:
    return isinstance(name, str) and name.strip().lower().endswith(LORA_EXTS)


def _first_num(node: dict, keys, default: float = 1.0) -> float:
    for key in keys:
        value = node.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return default


def _coerce_lora(item) -> dict | None:
    if isinstance(item, str):
        name = _norm_lora_name(item)
        if not _looks_like_lora(name):
            return None
        return {"name": name, "strength_model": 1.0, "strength_clip": 1.0}
    if not isinstance(item, dict):
        return None
    name = ""
    for key in ("lora_name", "lora", "name", "path", "lora_path"):
        value = item.get(key)
        if _looks_like_lora(value):
            name = _norm_lora_name(value)
            break
    if not name:
        return None
    if item.get("on", item.get("enabled", True)) is False:
        return None
    strength = _first_num(item, ("strength_model", "model_strength", "strength", "weight"), 1.0)
    clip_strength = _first_num(item, ("strength_clip", "clip_strength"), strength)
    return {"name": name, "strength_model": strength, "strength_clip": clip_strength}


def _coerce_loose_lora(item) -> dict | None:
    """宽松版：兼容 LoraManager 这类 name 不带扩展名、用 active 标记的写法。"""
    if isinstance(item, str):
        name = _norm_lora_name(item)
        # 排除 "80" 这类被同名参数误当成 LoRA 的纯数字值
        if not name or name.isdigit() or len(name) < 2:
            return None
        return {"name": name, "strength_model": 1.0, "strength_clip": 1.0}
    if not isinstance(item, dict):
        return None
    if item.get("hidden") is True:
        return None
    if item.get("active", item.get("on", item.get("enabled", True))) is False:
        return None
    name = ""
    for key in ("lora", "lora_name", "display_name", "path", "lora_path", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            name = _norm_lora_name(value)
            break
    if not name:
        return None
    marker = (
        _looks_like_lora(name)
        or any(key in item for key in ("clipStrength", "strength_model", "strength_clip", "modelStrength", "weight"))
        or ("active" in item and "strength" in item)
    )
    if not marker:
        return None
    strength = _first_num(item, ("strength", "strength_model", "model_strength", "weight"), 1.0)
    clip_strength = _first_num(item, (
        "clipStrength", "clip_strength", "strength_clip", "text_encoder_weight",
    ), strength)
    return {"name": name, "strength_model": strength, "strength_clip": clip_strength}


def _coerce_loras(data) -> list[dict]:
    if isinstance(data, dict):
        if isinstance(data.get("loras"), list):
            return _coerce_loras(data["loras"])
        single = _coerce_loose_lora(data)
        return [single] if single else []
    if isinstance(data, list):
        return [item for item in (_coerce_loose_lora(entry) for entry in data) if item]
    return []


def _merge_loras(*groups) -> list[dict]:
    order: list[str] = []
    merged: dict[str, dict] = {}
    for group in groups:
        for item in group or []:
            name = item.get("name")
            if not name:
                continue
            if name not in merged:
                order.append(name)
                merged[name] = dict(item)
            else:
                merged[name].update(item)
    return [merged[name] for name in order]


def _parse_lora_tags(text) -> list[dict]:
    items = []
    for name, weight, clip_weight in LORA_TAG_RE.findall(str(text or "")):
        name = _norm_lora_name(name)
        if not name:
            continue
        try:
            value = float(weight)
        except ValueError:
            value = 1.0
        clip = value
        if clip_weight:
            try:
                clip = float(clip_weight)
            except ValueError:
                pass
        items.append({"name": name, "strength_model": value, "strength_clip": clip})
    return items


def _format_lora_tags(items, include_clip: bool = True) -> str:
    """把 LoRA 列表转成 <lora:名字:权重> 文本，可直接接 LoraManager 的语法输入。"""
    parts = []
    for item in items or []:
        name = str(item.get("name") or "")
        if not name:
            continue
        name = re.sub(r"\.(?:safetensors|pt|pth|ckpt|bin)$", "", name, flags=re.IGNORECASE)
        model = float(item.get("strength_model", 1.0))
        clip = float(item.get("strength_clip", model))
        if include_clip and abs(model - clip) > 1e-6:
            parts.append(f"<lora:{name}:{model:g}:{clip:g}>")
        else:
            parts.append(f"<lora:{name}:{model:g}>")
    return " ".join(parts)


def _parse_lora_input(raw) -> list[dict]:
    """接受 LoRA 组合 JSON、<lora:...> 文本或普通名称列表。"""
    if isinstance(raw, list):
        return _coerce_loras(raw)
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return _coerce_loras(data)
        if isinstance(data, dict) and isinstance(data.get("loras"), list):
            return _coerce_loras(data["loras"])
    except Exception:
        pass
    return _parse_lora_tags(text)


def _strip_lora_tags(text) -> str:
    """提示词里的 <lora:...> 已经归到 LoRA 区，正文里去掉。"""
    cleaned = LORA_TAG_RE.sub("", str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _collect_scattered_loras(node) -> list[dict]:
    """兼容 lora_01 / LoRA名称_1 这类把文件名直接放在字符串字段里的堆叠节点。"""
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return []
    found = []
    for key, value in inputs.items():
        # lora_str 这类 JSON 数组字符串（WeiLin 等节点）
        if isinstance(value, str) and "lora" in str(key).lower():
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
                if isinstance(parsed, list):
                    found.extend(_coerce_loras(parsed))
                    continue

        match = LORA_KEY_RE.match(str(key))
        if not match or not isinstance(value, str) or not _looks_like_lora(value):
            continue
        index = match.group(1)
        strength = _first_num(inputs, (
            f"strength_{index}", f"strength_model_{index}", f"strength{index}",
            f"LoRA强度_{index}", f"权重_{index}",
        ), 1.0)
        clip_strength = _first_num(inputs, (
            f"strength_clip_{index}", f"clip_strength_{index}", f"clipStrength_{index}",
        ), strength)
        found.append({
            "name": _norm_lora_name(value),
            "strength_model": strength,
            "strength_clip": clip_strength,
        })
    return found


def _collect_loras_from_prompt(prompt) -> list[dict]:
    """扫描 API 工作流：LoRA 节点、LoraManager 的 loras 列表、任意 <lora:...> 文本。"""
    found: list[dict] = []
    if not isinstance(prompt, dict):
        return found

    def walk(node, in_lora_manager=False):
        if isinstance(node, dict):
            class_type = str(node.get("class_type") or "").lower().replace(" ", "")
            manager = in_lora_manager or "loramanager" in class_type
            loras_field = node.get("loras")
            if isinstance(loras_field, list):
                found.extend(_coerce_loras(loras_field))
            single = _coerce_lora(node)
            if single:
                found.append(single)
            if "class_type" in node:
                found.extend(_collect_scattered_loras(node))
            for key, value in node.items():
                if isinstance(value, str):
                    # LoraManager 的 text 是完整组合（含未启用项），不看它
                    if manager and key == "text":
                        continue
                    if "<lora:" in value.lower():
                        found.extend(_parse_lora_tags(value))
                else:
                    walk(value, manager)
        elif isinstance(node, list):
            for value in node:
                walk(value, in_lora_manager)

    walk(prompt)
    return found


def _collect_loras_from_workflow(workflow) -> list[dict]:
    """扫描 UI 工作流的 widgets_values（兼容 LoraManager / rgthree 结构）。"""
    found: list[dict] = []
    if not isinstance(workflow, dict):
        return found

    def walk(node):
        if isinstance(node, dict):
            loras_field = node.get("loras")
            if isinstance(loras_field, list):
                found.extend(_coerce_loras(loras_field))
            widgets = node.get("widgets_values")
            if isinstance(widgets, list):
                for value in widgets:
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        found.extend(_coerce_loras(value))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    walk(value)

    walk(workflow)
    return found


# ---------------------------------------------------------------------------
# 复杂工作流 / A1111 参数的提示词提取
# ---------------------------------------------------------------------------
def _looks_like_prompt(value) -> bool:
    text = str(value or "").strip()
    if len(text) < 20:
        return False
    if re.fullmatch(r"[\d\s.,+\-*/]+", text):
        return False
    return True


def _workflow_texts(workflow) -> tuple[str, str]:
    """从 UI 格式 workflow 沿采样器的 positive / negative 连线回溯文本。"""
    if not isinstance(workflow, dict):
        return "", ""
    nodes = {}
    for node in workflow.get("nodes") or []:
        if isinstance(node, dict) and "id" in node:
            nodes[node["id"]] = node

    links = {}
    for link in workflow.get("links") or []:
        if isinstance(link, list) and len(link) >= 5:
            links[link[0]] = link
        elif isinstance(link, dict) and link.get("id") is not None:
            links[link["id"]] = [
                link.get("id"), link.get("origin_id"), link.get("origin_slot"),
                link.get("target_id"), link.get("target_slot"), link.get("type"),
            ]

    def widget_text(node, relaxed=False) -> str:
        widgets = node.get("widgets_values")
        if not isinstance(widgets, list):
            return ""
        for value in widgets:
            if isinstance(value, str) and value.strip():
                if relaxed or _looks_like_prompt(value):
                    return value.strip()
        return ""

    def resolve(link_id, depth=0) -> str:
        if depth > 12 or link_id is None:
            return ""
        entry = links.get(link_id)
        if not entry:
            return ""
        node = nodes.get(entry[1])
        if not isinstance(node, dict):
            return ""

        node_type = str(node.get("type") or "").lower()
        if "cliptextencode" in node_type or "textencode" in node_type:
            text = widget_text(node, relaxed=True)
            if text:
                return text

        inputs = [item for item in (node.get("inputs") or []) if isinstance(item, dict)]
        preferred = ("conditioning", "text", "positive", "negative", "clip")
        for item in sorted(inputs, key=lambda entry: 0 if entry.get("name") in preferred else 1):
            if item.get("link") is None:
                continue
            text = resolve(item["link"], depth + 1)
            if text:
                return text

        if "string" in node_type or "text" in node_type or "primitive" in node_type:
            return widget_text(node, relaxed=True)
        return widget_text(node)

    for node in nodes.values():
        node_type = str(node.get("type") or "").lower()
        if "ksampler" not in node_type and "sampler" not in node_type:
            continue
        inputs = {
            item.get("name"): item
            for item in (node.get("inputs") or [])
            if isinstance(item, dict) and item.get("name")
        }
        positive = resolve((inputs.get("positive") or {}).get("link"))
        negative = resolve((inputs.get("negative") or {}).get("link"))
        if positive or negative:
            return positive, negative
    return "", ""


def _parse_a1111_parameters(text) -> dict:
    """解析 A1111 / WebUI 风格的 parameters 文本块。"""
    result = {"positive": "", "negative": "", "seed": None, "checkpoint": "", "loras": []}
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return result

    params_match = re.search(r"(?m)^Steps:\s", raw)
    head = raw[:params_match.start()].rstrip() if params_match else raw
    params = raw[params_match.start():] if params_match else ""

    negative_match = re.search(r"(?m)^Negative prompt:\s*", head)
    if negative_match:
        result["positive"] = head[:negative_match.start()].strip()
        result["negative"] = head[negative_match.end():].strip()
    else:
        result["positive"] = head.strip()

    seed = re.search(r"(?i)\bSeed:\s*(\d+)", params)
    if seed:
        try:
            result["seed"] = int(seed.group(1))
        except ValueError:
            pass
    model = re.search(r"(?i)\bModel:\s*([^,\n]+)", params)
    if model:
        result["checkpoint"] = model.group(1).strip()
    for name in re.findall(r"LORA:([^\"\s,{}]+\.(?:safetensors|pt|pth|ckpt|bin))", params, re.I):
        result["loras"].append({
            "name": _norm_lora_name(name), "strength_model": 1.0, "strength_clip": 1.0,
        })
    return result


# ---------------------------------------------------------------------------
# 图片 / 提示词读取
# ---------------------------------------------------------------------------
def _read_png_text(path: Path) -> dict:
    if path.suffix.lower() != ".png":
        return {}
    try:
        with Image.open(path) as image:
            info = dict(getattr(image, "text", {}) or {})
            info.update({key: value for key, value in image.info.items() if isinstance(value, str)})
            return info
    except Exception:
        return {}


def _load_image_tensor(path: Path) -> torch.Tensor:
    frames = []
    with Image.open(path) as source:
        size = None
        for frame in ImageSequence.Iterator(source):
            image = frame.convert("RGB")
            if size is None:
                size = image.size
            elif image.size != size:
                continue
            array = np.asarray(image, dtype=np.float32) / 255.0
            frames.append(torch.from_numpy(array).unsqueeze(0))
    if not frames:
        raise ValueError(f"无法读取图片：{path.name}")
    return torch.cat(frames, dim=0)


def read_prompt(path: Path) -> dict:
    """按 txt -> png 元数据 -> 同名 json -> png 原生工作流 的顺序取提示词，并解析所用 LoRA。"""
    data = {"positive": "", "negative": "", "checkpoint": "", "seed": None,
            "loras": [], "source": ""}

    txt = path.with_suffix(".txt")
    if txt.is_file():
        try:
            data["positive"] = txt.read_text(encoding="utf-8").strip()
            if data["positive"]:
                data["source"] = "txt"
        except OSError:
            pass

    meta = {}
    sidecar = path.with_suffix(".json")
    if sidecar.is_file():
        try:
            parsed = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(parsed, dict) and str(parsed.get("schema") or "").startswith("prompt-vault"):
                meta = parsed
        except Exception:
            meta = {}

    png_text = _read_png_text(path)
    if not meta and png_text.get(META_KEY):
        try:
            parsed = json.loads(png_text[META_KEY])
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            pass

    if meta:
        if not data["positive"]:
            data["positive"] = str(meta.get("prompt") or "")
            if data["positive"]:
                data["source"] = data["source"] or "metadata"
        data["negative"] = str(meta.get("negative") or "")
        data["checkpoint"] = str(meta.get("checkpoint") or "")
        data["seed"] = meta.get("seed")
        data["loras"] = _coerce_loras(meta.get("loras"))

    native = {}
    if png_text.get("prompt"):
        try:
            parsed = json.loads(png_text["prompt"])
            if isinstance(parsed, dict):
                native = parsed
        except Exception:
            native = {}

    if native:
        if not data["positive"]:
            positive, negative = _sampler_texts(native)
            data["positive"] = positive
            data["negative"] = data["negative"] or negative
            if data["positive"]:
                data["source"] = data["source"] or "workflow"
        extras = _workflow_extras(native)
        data["checkpoint"] = data["checkpoint"] or extras["checkpoint"]
        if data["seed"] is None:
            data["seed"] = extras["seed"]

    # A1111 / WebUI 风格的 parameters 文本块
    a1111 = {"positive": "", "negative": "", "seed": None, "checkpoint": "", "loras": []}
    if not data["positive"] and png_text.get("parameters"):
        a1111 = _parse_a1111_parameters(png_text["parameters"])
        data["positive"] = a1111["positive"]
        data["negative"] = data["negative"] or a1111["negative"]
        if data["seed"] is None:
            data["seed"] = a1111["seed"]
        data["checkpoint"] = data["checkpoint"] or a1111["checkpoint"]
        if data["positive"]:
            data["source"] = data["source"] or "a1111"

    # UI 格式 workflow：处理提示词来自其它节点（K2、PrimitiveString、LoraManager 等）
    workflow = {}
    if png_text.get("workflow"):
        try:
            parsed = json.loads(png_text["workflow"])
            if isinstance(parsed, dict):
                workflow = parsed
        except Exception:
            workflow = {}

    if not data["positive"] or not data["negative"]:
        workflow_positive, workflow_negative = _workflow_texts(workflow)
        data["positive"] = data["positive"] or workflow_positive
        data["negative"] = data["negative"] or workflow_negative
        if data["positive"]:
            data["source"] = data["source"] or "workflow"

    # 负向用的是同一条文本时（ConditioningZeroOut 之类），视为没有负向
    if data["negative"] and data["negative"] == data["positive"]:
        data["negative"] = ""

    tag_loras = _parse_lora_tags(f"{data['positive']}\n{data['negative']}")
    data["loras"] = _merge_loras(
        data["loras"],
        _collect_loras_from_prompt(native),
        _coerce_loras(a1111.get("loras")),
        _collect_loras_from_workflow(workflow),
        tag_loras,
    )
    data["positive"] = _strip_lora_tags(data["positive"])
    data["negative"] = _strip_lora_tags(data["negative"])
    return data


def _resolve_image_path(image_path) -> Path:
    text = str(image_path or "").strip()
    if not text:
        raise ValueError("请先在节点下方的图库面板选择图片，或填写图片绝对路径")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = Path(folder_paths.get_output_directory()) / path
    if not path.is_file():
        raise ValueError(f"找不到图片：{path}")
    return path


def _resolve_save_dir(value) -> Path:
    text = str(value or "").strip()
    if not text or text in ("默认", "default", "Default"):
        return Path(folder_paths.get_output_directory())
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("保存位置必须是绝对目录，例如 F:\\images")
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# 节点：保存
# ---------------------------------------------------------------------------
class PromptVaultSave:
    def __init__(self):
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": DEFAULT_PREFIX}),
                "save_location": ("STRING", {"default": "默认",
                                             "tooltip": "留空或填「默认」保存到 ComfyUI output 目录；也可填绝对目录。"}),
            },
            "optional": {
                "positive_prompt": ("STRING", {"forceInput": True,
                                               "tooltip": "正向提示词；不接则自动从采样器连线回溯。"}),
                "negative_prompt": ("STRING", {"forceInput": True,
                                               "tooltip": "负向提示词；不接则自动回溯。"}),
                "save_txt": ("BOOLEAN", {"default": True, "tooltip": "在图片旁写一个同名 .txt 提示词文件。"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "漓月"
    DESCRIPTION = "保存图片，同时写入同名 .txt 提示词，并把提示词记入 PNG 元数据。"

    def save_images(
        self,
        images,
        filename_prefix=DEFAULT_PREFIX,
        save_location="默认",
        positive_prompt=None,
        negative_prompt=None,
        save_txt=True,
        prompt=None,
        extra_pnginfo=None,
    ):
        if images is None:
            raise ValueError("请先连接 images 输入")

        prefix = str(filename_prefix or "").strip()
        prefix = INVALID_FILENAME_RE.sub("_", prefix).strip(" .") or DEFAULT_PREFIX
        save_dir = _resolve_save_dir(save_location)

        first = images[0]
        full_folder, stem, counter, _subfolder, _ = folder_paths.get_save_image_path(
            prefix, str(save_dir), int(first.shape[1]), int(first.shape[0])
        )

        sampler_positive, sampler_negative = _sampler_texts(prompt)
        extras = _workflow_extras(prompt)
        prompt_text = str(positive_prompt or "").strip() or sampler_positive
        negative_text = str(negative_prompt or "").strip() or sampler_negative

        output_root = Path(folder_paths.get_output_directory()).resolve()
        ui_images = []
        saved = []
        for batch_number, image in enumerate(images):
            array = 255.0 * image.detach().cpu().numpy()
            picture = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

            file_name = f"{stem.replace('%batch_num%', str(batch_number))}_{counter:05}_.png"
            out_path = Path(full_folder) / file_name
            counter += 1

            metadata = None
            if not args.disable_metadata:
                metadata = PngInfo()
                if prompt is not None:
                    metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for key, value in extra_pnginfo.items():
                        metadata.add_text(key, json.dumps(value))
                metadata.add_text(META_KEY, json.dumps({
                    "schema": SCHEMA,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "prompt": prompt_text,
                    "negative": negative_text,
                    "checkpoint": extras["checkpoint"],
                    "seed": extras["seed"],
                    "width": int(picture.width),
                    "height": int(picture.height),
                }, ensure_ascii=False))

            picture.save(out_path, pnginfo=metadata, compress_level=self.compress_level)

            if save_txt and prompt_text:
                out_path.with_suffix(".txt").write_text(prompt_text, encoding="utf-8")

            try:
                relative = out_path.resolve().relative_to(output_root)
                ui_images.append({
                    "filename": relative.name,
                    "subfolder": "" if str(relative.parent) == "." else relative.parent.as_posix(),
                    "type": "output",
                })
            except ValueError:
                pass
            saved.append({"path": str(out_path), "chars": len(prompt_text)})

        return {
            "ui": {
                "images": ui_images,
                "prompt_vault_saved": [json.dumps(item, ensure_ascii=False) for item in saved],
            },
            "result": (images,),
        }


# ---------------------------------------------------------------------------
# 节点：提取
# ---------------------------------------------------------------------------
class PromptVaultLoad:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_path": ("STRING", {"default": "",
                                          "tooltip": "由节点下方的图库面板自动填写，也可直接填图片绝对路径。"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "正向提示词", "负向提示词", "LoRA组合", "元数据(JSON)")
    FUNCTION = "load"
    CATEGORY = "漓月"
    DESCRIPTION = "从图库面板选择图片，输出图片和它保存的提示词。"

    @classmethod
    def IS_CHANGED(cls, image_path=""):
        try:
            path = _resolve_image_path(image_path)
            stat = path.stat()
            txt = path.with_suffix(".txt")
            txt_stamp = txt.stat().st_mtime_ns if txt.is_file() else 0
            return f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{txt_stamp}"
        except Exception:
            return float("nan")

    def load(self, image_path=""):
        path = _resolve_image_path(image_path)
        image = _load_image_tensor(path)
        info = read_prompt(path)

        meta = {
            "schema": SCHEMA,
            "source": str(path),
            "prompt_source": info["source"],
            "checkpoint": info["checkpoint"],
            "seed": info["seed"],
            "width": int(image.shape[2]),
            "height": int(image.shape[1]),
        }
        return (
            image,
            info["positive"],
            info["negative"],
            _format_lora_tags(info["loras"]),
            json.dumps(meta, ensure_ascii=False),
        )


class PromptVaultLoraApply:
    def __init__(self):
        self._cache: dict[str, tuple[float, object, object]] = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "loras": ("STRING", {"forceInput": True,
                                     "tooltip": "接「LoRA组合」输出（JSON），也接受 <lora:名:权重> 文本。"}),
                "enabled": ("BOOLEAN", {"default": True}),
                "skip_missing": ("BOOLEAN", {"default": True,
                                             "tooltip": "关闭后遇到缺失的 LoRA 直接报错。"}),
            },
            "optional": {
                "clip": ("CLIP",),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("模型", "CLIP", "应用报告")
    FUNCTION = "apply_loras"
    CATEGORY = "漓月"
    DESCRIPTION = "按 LoRA 组合 JSON 依次加载 LoRA，输出叠加后的 MODEL / CLIP。"

    def _resolve_path(self, name: str):
        normalized = _norm_lora_name(name)
        if not normalized:
            return None

        # 1. 完整相对路径（可含子文件夹、可带扩展名）
        path = folder_paths.get_full_path("loras", normalized)
        if path:
            return path

        # 2. 没写扩展名时逐个补上再试
        if not normalized.lower().endswith(LORA_EXTS):
            for ext in LORA_EXTS:
                candidate = folder_paths.get_full_path("loras", normalized + ext)
                if candidate:
                    return candidate

        # 3. 按文件名在所有子文件夹里找（忽略目录层级与扩展名）
        base = Path(normalized).name.lower()
        stem = Path(base).stem
        for relative in folder_paths.get_filename_list("loras"):
            relative_name = Path(relative).name.lower()
            if relative_name == base or Path(relative_name).stem == stem:
                return folder_paths.get_full_path("loras", relative)
        return None

    def apply_loras(self, model, loras, enabled=True, skip_missing=True, clip=None):
        items = _parse_lora_input(loras)
        if not enabled:
            return (model, clip, "未启用，原样输出")
        if not items:
            return (model, clip, "LoRA 组合为空，原样输出")
        if model is None:
            return (model, clip, "没有 MODEL 输入，原样输出")

        import comfy.sd
        import comfy.utils

        report = []
        for item in items:
            name = str(item.get("name") or "")
            if not name:
                continue
            strength_model = float(item.get("strength_model", 1.0))
            strength_clip = float(item.get("strength_clip", strength_model))
            if strength_model == 0 and strength_clip == 0:
                report.append(f"跳过 {name}（强度为 0）")
                continue

            path = self._resolve_path(name)
            if not path:
                if not skip_missing:
                    raise FileNotFoundError(f"LoRA 不存在：{name}")
                report.append(f"缺失 {name}")
                continue

            try:
                modified = os.path.getmtime(path)
            except OSError:
                modified = 0.0
            cached = self._cache.get(path)
            if cached and cached[0] == modified:
                lora, metadata = cached[1], cached[2]
            else:
                lora, metadata = comfy.utils.load_torch_file(path, safe_load=True, return_metadata=True)
                self._cache[path] = (modified, lora, metadata)

            model, clip = comfy.sd.load_lora_for_models(
                model, clip, lora, strength_model, strength_clip, lora_metadata=metadata
            )
            report.append(f"已加载 {name}（model {strength_model:g} / clip {strength_clip:g}）")

        return (model, clip, "\n".join(report) or "没有可应用的 LoRA")


NODE_CLASS_MAPPINGS = {
    "PromptVaultLoad": PromptVaultLoad,
    "PromptVaultLoraApply": PromptVaultLoraApply,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptVaultLoad": "图库提取",
    "PromptVaultLoraApply": "应用 LoRA 组合",
}
