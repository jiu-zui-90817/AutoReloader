"""
工程管理
- 合并 / 单文件双模式
- 可编辑文件列表 = 配置主文件 + #include 拆分文件（不扫地图等无关 ini）
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .csf_parser import CsfParser
from .ini_parser import IniDocument, load_ini_with_includes
from .save_util import backup_file, write_section_to_file

# Placeholder - full content will be in next attempt if this fails
