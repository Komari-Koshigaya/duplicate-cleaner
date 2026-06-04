"""
配置管理单元测试

测试配置的加载、保存、验证和默认值。
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from duplicate_cleaner.config import AppConfig, FONT_SIZES, WINDOW_SIZES, FILE_FILTERS


@pytest.fixture
def temp_config_dir(tmp_path):
    """创建临时配置目录"""
    with patch('duplicate_cleaner.config.get_config_file') as mock:
        config_file = tmp_path / "config.json"
        mock.return_value = config_file
        yield config_file


class TestAppConfig:
    """AppConfig 类测试"""

    def test_default_values(self):
        """测试默认配置值"""
        config = AppConfig()
        assert config.font_size == "中"
        assert config.window_size == "大"
        assert config.sound_enabled is False
        assert config.last_dir == ""
        assert config.recent_dirs == []
        assert config.recursive is True
        assert config.min_size == "0"
        assert config.file_filter == "所有文件"
        assert config.single_instance is True

    def test_save_and_load(self, temp_config_dir):
        """测试保存和加载"""
        config = AppConfig()
        config.last_dir = "/test/path"
        config.font_size = "大"
        config.sound_enabled = True
        config.save()

        loaded = AppConfig.load()
        assert loaded.last_dir == "/test/path"
        assert loaded.font_size == "大"
        assert loaded.sound_enabled is True

    def test_load_nonexistent(self, temp_config_dir):
        """测试加载不存在的配置文件"""
        config = AppConfig.load()
        assert config.font_size == "中"  # 使用默认值

    def test_load_corrupted_json(self, temp_config_dir):
        """测试加载损坏的 JSON 文件"""
        temp_config_dir.write_text("not valid json", encoding='utf-8')
        config = AppConfig.load()
        assert config.font_size == "中"  # 使用默认值

    def test_load_missing_fields(self, temp_config_dir):
        """测试加载缺少字段的配置"""
        temp_config_dir.write_text('{"font_size": "大"}', encoding='utf-8')
        config = AppConfig.load()
        assert config.font_size == "大"
        assert config.window_size == "大"  # 使用默认值

    def test_save_creates_directory(self, tmp_path):
        """测试保存时自动创建目录"""
        config_file = tmp_path / "subdir" / "config.json"
        with patch('duplicate_cleaner.config.get_config_file', return_value=config_file):
            config = AppConfig()
            config.save()
            assert config_file.exists()

    def test_add_recent_dir(self):
        """测试添加最近目录"""
        config = AppConfig()
        config.add_recent_dir("/path/a")
        config.add_recent_dir("/path/b")
        assert config.recent_dirs == ["/path/b", "/path/a"]

    def test_add_recent_dir_dedup(self):
        """测试最近目录去重"""
        config = AppConfig()
        config.add_recent_dir("/path/a")
        config.add_recent_dir("/path/b")
        config.add_recent_dir("/path/a")  # 重复
        assert config.recent_dirs == ["/path/a", "/path/b"]
        assert len(config.recent_dirs) == 2

    def test_add_recent_dir_limit(self):
        """测试最近目录数量限制"""
        config = AppConfig()
        for i in range(15):
            config.add_recent_dir(f"/path/{i}")
        assert len(config.recent_dirs) == 10
        assert config.recent_dirs[0] == "/path/14"

    def test_add_recent_dir_empty(self):
        """测试添加空目录"""
        config = AppConfig()
        config.add_recent_dir("")
        assert config.recent_dirs == []

    def test_get_filter_extensions(self):
        """测试获取过滤扩展名"""
        config = AppConfig()
        config.file_filter = "图片"
        exts = config.get_filter_extensions()
        assert ".jpg" in exts
        assert ".png" in exts

    def test_get_filter_extensions_unknown(self):
        """测试未知过滤类型"""
        config = AppConfig()
        config.file_filter = "未知类型"
        exts = config.get_filter_extensions()
        assert exts == []

    def test_get_font_config(self):
        """测试获取字体配置"""
        config = AppConfig()
        config.font_size = "大"
        font = config.get_font_config()
        assert font["base"] == 12
        assert font["title"] == 22

    def test_get_font_config_invalid(self):
        """测试无效字体大小"""
        config = AppConfig()
        config.font_size = "无效"
        font = config.get_font_config()
        assert font == FONT_SIZES["中"]  # 回退到默认

    def test_get_window_size(self):
        """测试获取窗口大小"""
        config = AppConfig()
        config.window_size = "大"
        w, h = config.get_window_size()
        assert w == 1700
        assert h == 1100

    def test_validate_valid(self):
        """测试验证有效配置"""
        config = AppConfig()
        warnings = config.validate()
        assert warnings == []

    def test_validate_invalid_font_size(self):
        """测试验证无效字体大小"""
        config = AppConfig()
        config.font_size = "无效"
        warnings = config.validate()
        assert len(warnings) > 0
        assert config.font_size == "中"

    def test_validate_invalid_window_size(self):
        """测试验证无效窗口大小"""
        config = AppConfig()
        config.window_size = "无效"
        warnings = config.validate()
        assert len(warnings) > 0
        assert config.window_size == "大"

    def test_validate_invalid_min_size(self):
        """测试验证无效最小文件大小"""
        config = AppConfig()
        config.min_size = "abc"
        warnings = config.validate()
        assert len(warnings) > 0
        assert config.min_size == "0"


class TestConstants:
    """常量测试"""

    def test_font_sizes_keys(self):
        """测试字体大小配置键"""
        assert "小" in FONT_SIZES
        assert "中" in FONT_SIZES
        assert "大" in FONT_SIZES

    def test_window_sizes_keys(self):
        """测试窗口大小配置键"""
        assert "小" in WINDOW_SIZES
        assert "中" in WINDOW_SIZES
        assert "大" in WINDOW_SIZES

    def test_file_filters_keys(self):
        """测试文件类型过滤键"""
        assert "所有文件" in FILE_FILTERS
        assert "图片" in FILE_FILTERS
        assert "视频" in FILE_FILTERS

    def test_all_filter_has_empty_extensions(self):
        """测试"所有文件"过滤为空列表"""
        assert FILE_FILTERS["所有文件"] == []
