"""
公共工具函数模块

提供格式化、日志、路径等通用功能，供 CLI 和 GUI 共同使用。
"""

import os
import sys
import logging
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime


# ==================== 路径工具 ====================

def get_app_data_dir() -> Path:
    """
    获取应用数据存储目录

    Windows: %APPDATA%/DuplicateCleaner
    Linux/Mac: ~/.config/duplicate-cleaner

    Returns:
        应用数据目录 Path 对象
    """
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "DuplicateCleaner"
        return Path.home() / ".duplicate_cleaner"
    else:
        return Path.home() / ".config" / "duplicate-cleaner"


def get_config_file() -> Path:
    """获取配置文件完整路径"""
    return get_app_data_dir() / "config.json"


def get_lock_file() -> Path:
    """获取锁文件完整路径（用于单实例模式）"""
    return get_app_data_dir() / ".lock"


def get_log_file() -> Path:
    """获取日志文件路径"""
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"duplicate_cleaner_{datetime.now().strftime('%Y%m%d')}.log"


# ==================== 日志配置 ====================

def setup_logging(name: str = "duplicate_cleaner", level: int = logging.INFO) -> logging.Logger:
    """
    配置日志系统（同时输出到控制台和文件）

    Args:
        name: 日志器名称
        level: 日志级别

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出
    try:
        log_file = get_log_file()
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info(f"日志文件: {log_file}")
    except Exception as e:
        logger.warning(f"无法创建日志文件: {e}")

    return logger


# 默认日志器
logger = setup_logging()


def ensure_dir_exists(path: Path) -> None:
    """确保目录存在，不存在则创建"""
    path.mkdir(parents=True, exist_ok=True)


def get_backup_dir() -> Path:
    """获取配置备份目录"""
    return get_app_data_dir() / "backups"


def backup_config() -> Optional[Path]:
    """
    备份配置文件

    Returns:
        备份文件路径，失败返回 None
    """
    config_file = get_config_file()
    if not config_file.exists():
        return None

    try:
        backup_dir = get_backup_dir()
        ensure_dir_exists(backup_dir)

        # 备份文件名带时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"config_{timestamp}.json"

        shutil.copy2(config_file, backup_file)

        # 只保留最近 10 个备份
        backups = sorted(backup_dir.glob("config_*.json"), reverse=True)
        for old_backup in backups[10:]:
            old_backup.unlink()

        return backup_file
    except Exception:
        return None


def restore_config(backup_file: Path) -> bool:
    """
    恢复配置文件

    Args:
        backup_file: 备份文件路径

    Returns:
        True 恢复成功，False 恢复失败
    """
    try:
        config_file = get_config_file()
        ensure_dir_exists(config_file.parent)
        shutil.copy2(backup_file, config_file)
        return True
    except Exception:
        return False


def list_backups() -> list:
    """
    列出所有配置备份

    Returns:
        备份文件路径列表（按时间倒序）
    """
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("config_*.json"), reverse=True)


# ==================== 格式化工具 ====================

def format_size(size_bytes: int) -> str:
    """
    将字节数格式化为人类可读的文件大小

    Args:
        size_bytes: 文件大小（字节）

    Returns:
        格式化后的字符串，如 "1.5 MB"

    Examples:
        >>> format_size(0)
        '0.0 B'
        >>> format_size(1024)
        '1.0 KB'
        >>> format_size(1048576)
        '1.0 MB'
    """
    if size_bytes < 0:
        return f"-{format_size(-size_bytes)}"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_bytes)

    for unit in units:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} PB"


def is_send2trash_available() -> bool:
    """
    检查 send2trash 是否可用

    Returns:
        True 如果 send2trash 已安装且可导入
    """
    try:
        import send2trash  # noqa: F401
        return True
    except ImportError:
        return False
