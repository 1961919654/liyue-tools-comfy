# -*- coding: utf-8 -*-
"""Prompt Vault：提示词的保存 / 图库提取。"""

from .prompt_vault import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

try:
    from . import routes as _routes  # noqa: F401
except Exception:
    _routes = None

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
