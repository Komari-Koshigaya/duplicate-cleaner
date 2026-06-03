"""
配置管理模块

负责应用配置的加载、保存和默认值管理。
配置文件使用 JSON 格式存储在用户应用数据目录。
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field

from .utils import get_config_file, ensure_dir_exists

logger = logging.getLogger("duplicate_cleaner")

# 默认配置值
DEFAULT_FONT_SIZE = "中"
DEFAULT_WINDOW_SIZE = "中"
DEFAULT_SOUND_ENABLED = False
DEFAULT_RECURSIVE = True
DEFAULT_MIN_SIZE = "0"
DEFAULT_FILE_FILTER = "所有文件"
DEFAULT_SINGLE_INSTANCE = True

# 文件类型扩展名映射
FILE_FILTERS = {
    "所有文件": [],
    "图片": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff"],
    "视频": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"],
    "音频": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    "文档": [".doc", ".docx", ".pdf", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"],
    "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
}

# 字体大小配置
FONT_SIZES = {
    "小": {"base": 9, "title": 16, "tree": 9, "row": 24},
    "中": {"base": 10, "title": 18, "tree": 10, "row": 28},
    "大": {"base": 12, "title": 22, "tree": 12, "row": 34},
}

# 窗口大小配置
WINDOW_SIZES = {
    "小": (1100, 700),
    "中": (1400, 900),
    "大": (1700, 1100),
}


@dataclass
class AppConfig:
    """
    应用配置数据类

    所有配置项都有默认值，支持从 JSON 文件加载和保存。

    Attributes:
        font_size: 字体大小（小/中/大）
        window_size: 窗口大小（小/中/大）
        sound_enabled: 扫描完成是否播放提示音
        last_dir: 上次扫描的目录
        recent_dirs: 最近扫描的目录列表（最多 10 个）
        recursive: 是否递归扫描子目录
        min_size: 最小文件大小（字节字符串）
        file_filter: 文件类型过滤名称
        single_instance: 是否单实例模式
        dark_mode: 是否深色模式
    """
    font_size: str = DEFAULT_FONT_SIZE
    window_size: str = DEFAULT_WINDOW_SIZE
    sound_enabled: bool = DEFAULT_SOUND_ENABLED
    last_dir: str = ""
    recent_dirs: List[str] = field(default_factory=list)
    recursive: bool = DEFAULT_RECURSIVE
    min_size: str = DEFAULT_MIN_SIZE
    file_filter: str = DEFAULT_FILE_FILTER
    single_instance: bool = DEFAULT_SINGLE_INSTANCE
    dark_mode: bool = False

    def save(self) -> bool:
        """
        保存配置到文件

        Returns:
            True 保存成功，False 保存失败
        """
        config_file = get_config_file()
        try:
            ensure_dir_exists(config_file.parent)

            data = {
                "font_size": self.font_size,
                "window_size": self.window_size,
                "sound_enabled": self.sound_enabled,
                "last_dir": self.last_dir,
                "recent_dirs": self.recent_dirs[:10],  # 只保留最近 10 个
                "recursive": self.recursive,
                "min_size": self.min_size,
                "file_filter": self.file_filter,
                "single_instance": self.single_instance,
                "dark_mode": self.dark_mode,
            }

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"配置已保存: {config_file}")
            return True

        except (OSError, TypeError) as e:
            logger.error(f"保存配置失败: {e}")
            return False

    @classmethod
    def load(cls) -> 'AppConfig':
        """
        从文件加载配置

        如果文件不存在或解析失败，返回默认配置。

        Returns:
            AppConfig 实例
        """
        config_file = get_config_file()

        if not config_file.exists():
            logger.info("配置文件不存在，使用默认配置")
            return cls()

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            config = cls(
                font_size=data.get("font_size", DEFAULT_FONT_SIZE),
                window_size=data.get("window_size", DEFAULT_WINDOW_SIZE),
                sound_enabled=data.get("sound_enabled", DEFAULT_SOUND_ENABLED),
                last_dir=data.get("last_dir", ""),
                recent_dirs=data.get("recent_dirs", [])[:10],
                recursive=data.get("recursive", DEFAULT_RECURSIVE),
                min_size=data.get("min_size", DEFAULT_MIN_SIZE),
                file_filter=data.get("file_filter", DEFAULT_FILE_FILTER),
                single_instance=data.get("single_instance", DEFAULT_SINGLE_INSTANCE),
                dark_mode=data.get("dark_mode", False),
            )

            logger.debug(f"配置已加载: {config_file}")
            return config

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"配置文件解析失败，使用默认配置: {e}")
            return cls()
        except OSError as e:
            logger.error(f"读取配置文件失败: {e}")
            return cls()

    def add_recent_dir(self, directory: str) -> None:
        """
        添加目录到最近使用列表

        Args:
            directory: 目录路径
        """
        if not directory:
            return

        # 移除已存在的相同路径
        if directory in self.recent_dirs:
            self.recent_dirs.remove(directory)

        # 添加到列表开头
        self.recent_dirs.insert(0, directory)

        # 只保留最近 10 个
        self.recent_dirs = self.recent_dirs[:10]

    def get_filter_extensions(self) -> List[str]:
        """
        获取当前文件类型过滤的扩展名列表

        Returns:
            扩展名列表，空列表表示不过滤
        """
        return FILE_FILTERS.get(self.file_filter, [])

    def get_font_config(self) -> dict:
        """
        获取当前字体大小配置

        Returns:
            包含 base, title, tree, row 的字典
        """
        return FONT_SIZES.get(self.font_size, FONT_SIZES[DEFAULT_FONT_SIZE])

    def get_window_size(self) -> tuple:
        """
        获取当前窗口大小配置

        Returns:
            (width, height) 元组
        """
        return WINDOW_SIZES.get(self.window_size, WINDOW_SIZES[DEFAULT_WINDOW_SIZE])

    def validate(self) -> List[str]:
        """
        验证配置项的合法性

        Returns:
            警告信息列表，空列表表示配置合法
        """
        warnings = []

        if self.font_size not in FONT_SIZES:
            warnings.append(f"无效的字体大小: {self.font_size}，将使用默认值")
            self.font_size = DEFAULT_FONT_SIZE

        if self.window_size not in WINDOW_SIZES:
            warnings.append(f"无效的窗口大小: {self.window_size}，将使用默认值")
            self.window_size = DEFAULT_WINDOW_SIZE

        if self.file_filter not in FILE_FILTERS:
            warnings.append(f"无效的文件类型过滤: {self.file_filter}，将使用默认值")
            self.file_filter = DEFAULT_FILE_FILTER

        try:
            int(self.min_size)
        except ValueError:
            warnings.append(f"无效的最小文件大小: {self.min_size}，将使用 0")
            self.min_size = "0"

        return warnings
