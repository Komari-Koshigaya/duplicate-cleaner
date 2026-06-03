"""
工具函数单元测试

测试 format_size、路径工具等公共函数。
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from duplicate_cleaner.utils import format_size, get_app_data_dir, is_send2trash_available


class TestFormatSize:
    """format_size 函数测试"""

    def test_zero(self):
        """测试 0 字节"""
        assert format_size(0) == "0.0 B"

    def test_bytes(self):
        """测试字节级别"""
        assert format_size(1) == "1.0 B"
        assert format_size(512) == "512.0 B"
        assert format_size(1023) == "1023.0 B"

    def test_kilobytes(self):
        """测试 KB 级别"""
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"
        assert format_size(1024 * 1024 - 1) == "1024.0 KB"

    def test_megabytes(self):
        """测试 MB 级别"""
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 5) == "5.0 MB"

    def test_gigabytes(self):
        """测试 GB 级别"""
        assert format_size(1024 ** 3) == "1.0 GB"
        assert format_size(1024 ** 3 * 2.5) == "2.5 GB"

    def test_terabytes(self):
        """测试 TB 级别"""
        assert format_size(1024 ** 4) == "1.0 TB"

    def test_negative(self):
        """测试负数"""
        result = format_size(-1024)
        assert result.startswith("-")
        assert "1.0 KB" in result

    def test_large_number(self):
        """测试超大数字"""
        result = format_size(1024 ** 5)
        assert "PB" in result


class TestGetAppDataDir:
    """get_app_data_dir 函数测试"""

    def test_returns_path(self):
        """测试返回 Path 对象"""
        result = get_app_data_dir()
        assert isinstance(result, Path)

    @patch('sys.platform', 'win32')
    @patch.dict('os.environ', {'APPDATA': r'C:\Users\test\AppData\Roaming'})
    def test_windows_with_appdata(self):
        """测试 Windows 有 APPDATA 环境变量"""
        result = get_app_data_dir()
        assert "DuplicateCleaner" in str(result)

    @patch('sys.platform', 'win32')
    @patch.dict('os.environ', {'USERPROFILE': r'C:\Users\test'}, clear=True)
    def test_windows_without_appdata(self):
        """测试 Windows 无 APPDATA 环境变量"""
        result = get_app_data_dir()
        # 应回退到用户主目录
        assert "duplicate_cleaner" in str(result).lower() or "DuplicateCleaner" in str(result)

    @patch('sys.platform', 'linux')
    def test_linux(self):
        """测试 Linux 平台"""
        result = get_app_data_dir()
        assert ".config" in str(result)
        assert "duplicate-cleaner" in str(result)


class TestIsSend2TrashAvailable:
    """is_send2trash_available 函数测试"""

    def test_returns_bool(self):
        """测试返回布尔值"""
        result = is_send2trash_available()
        assert isinstance(result, bool)
