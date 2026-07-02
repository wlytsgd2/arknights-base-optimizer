"""
干员数据映射 - 从内置表获取干员中文名
"""
import json, os, sys

_char_map = None


def _get_data_path():
    """获取数据文件路径（兼容 PyInstaller 打包）"""
    # PyInstaller 打包后路径
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "char_table.json")
    # 正常 Python 运行
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "char_table.json")


def load():
    global _char_map
    if _char_map is not None:
        return _char_map

    path = _get_data_path()
    _char_map = {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, val in data.items():
            if isinstance(val, dict) and "name" in val:
                _char_map[key] = val["name"].strip()
    except FileNotFoundError:
        pass  # 文件不存在，返回空映射

    return _char_map


def get_name(char_id: str) -> str:
    m = load()
    if not m or not char_id:
        return char_id

    # 精确匹配
    if char_id in m:
        return m[char_id]

    # 去掉 char_ 前缀匹配
    if char_id.startswith("char_"):
        clean = char_id[5:]
        for key, name in m.items():
            if key.endswith(clean):
                return name

    return char_id
