"""
CLI 模块单元测试

测试命令行界面的各个函数。
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from duplicate_cleaner.scanner import ScanResult
from duplicate_cleaner.cli import display_duplicates, delete_files


@pytest.fixture
def sample_result():
    """创建示例扫描结果"""
    return ScanResult(
        duplicates=[
            ("abc123", ["/path/a.txt", "/path/b.txt"], 1024),
            ("def456", ["/path/x.jpg", "/path/y.jpg", "/path/z.jpg"], 2048),
        ],
        total_scanned=10,
        total_duplicates=5,
        total_wasted=5120
    )


@pytest.fixture
def empty_result():
    """创建空扫描结果"""
    return ScanResult()


class TestDisplayDuplicates:
    """display_duplicates 函数测试"""

    def test_display_empty(self, empty_result, capsys):
        """测试显示空结果"""
        display_duplicates(empty_result)
        captured = capsys.readouterr()
        assert "未发现重复文件" in captured.out

    def test_display_with_duplicates(self, sample_result, capsys):
        """测试显示有重复的结果"""
        display_duplicates(sample_result)
        captured = capsys.readouterr()
        assert "重复组 #1" in captured.out
        assert "重复组 #2" in captured.out
        assert "abc123" in captured.out
        assert "def456" in captured.out

    def test_display_statistics(self, sample_result, capsys):
        """测试显示统计信息"""
        display_duplicates(sample_result)
        captured = capsys.readouterr()
        assert "2 组重复" in captured.out
        assert "5 个重复文件" in captured.out


class TestDeleteFiles:
    """delete_files 函数测试"""

    def test_delete_empty_list(self):
        """测试删除空列表"""
        success, failed = delete_files([])
        assert success == 0
        assert failed == 0

    def test_dry_run(self, tmp_path, capsys):
        """测试预览模式"""
        file1 = tmp_path / "test1.txt"
        file1.write_text("content")

        success, failed = delete_files([str(file1)], dry_run=True)
        assert success == 1
        assert failed == 0
        assert file1.exists()  # 文件未被删除

        captured = capsys.readouterr()
        assert "预览" in captured.out

    def test_delete_single_file(self, tmp_path, capsys):
        """测试删除单个文件"""
        file1 = tmp_path / "test1.txt"
        file1.write_text("content")

        success, failed = delete_files([str(file1)])
        assert success == 1
        assert failed == 0
        assert not file1.exists()

    def test_delete_multiple_files(self, tmp_path, capsys):
        """测试删除多个文件"""
        files = []
        for i in range(3):
            f = tmp_path / f"test{i}.txt"
            f.write_text(f"content {i}")
            files.append(str(f))

        success, failed = delete_files(files)
        assert success == 3
        assert failed == 0

        for f in files:
            assert not os.path.exists(f)

    def test_delete_nonexistent_file(self, capsys):
        """测试删除不存在的文件"""
        success, failed = delete_files(["/nonexistent/file.txt"])
        assert success == 0
        assert failed == 1

    def test_delete_permission_error(self, tmp_path, capsys):
        """测试删除无权限文件"""
        file1 = tmp_path / "readonly.txt"
        file1.write_text("content")
        file1.chmod(0o444)  # 只读

        try:
            success, failed = delete_files([str(file1)])
            # 在某些系统上可能成功（权限检查不同）
            assert success + failed == 1
        finally:
            file1.chmod(0o644)  # 恢复权限以便清理

    @patch('duplicate_cleaner.cli.is_send2trash_available', return_value=True)
    @patch('send2trash.send2trash')
    def test_delete_to_trash(self, mock_send2trash, mock_available, tmp_path):
        """测试移到回收站"""
        file1 = tmp_path / "test.txt"
        file1.write_text("content")

        success, failed = delete_files([str(file1)], use_trash=True)
        assert success == 1
        mock_send2trash.assert_called_once_with(str(file1))
