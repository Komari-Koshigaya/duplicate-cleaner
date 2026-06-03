"""
扫描引擎单元测试

使用临时目录创建测试文件，验证扫描逻辑。
"""

import os
import pytest
import tempfile
from pathlib import Path

from duplicate_cleaner.scanner import FileScanner, ScanResult


@pytest.fixture
def scanner():
    """创建扫描器实例"""
    return FileScanner(max_workers=2)


@pytest.fixture
def test_dir():
    """创建临时测试目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_file(path: Path, content: bytes) -> Path:
    """创建测试文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestFileScanner:
    """FileScanner 类测试"""

    def test_empty_directory(self, scanner, test_dir):
        """测试空目录"""
        result = scanner.scan(str(test_dir))
        assert len(result.duplicates) == 0
        assert result.total_scanned == 0

    def test_no_duplicates(self, scanner, test_dir):
        """测试无重复文件"""
        create_file(test_dir / "a.txt", b"content a")
        create_file(test_dir / "b.txt", b"content b")

        result = scanner.scan(str(test_dir))
        assert len(result.duplicates) == 0
        assert result.total_scanned == 2

    def test_find_duplicates(self, scanner, test_dir):
        """测试查找重复文件"""
        content = b"same content"
        create_file(test_dir / "a.txt", content)
        create_file(test_dir / "b.txt", content)
        create_file(test_dir / "c.txt", b"different")

        result = scanner.scan(str(test_dir))
        assert len(result.duplicates) == 1
        assert result.total_duplicates == 2
        assert result.total_wasted == len(content)

    def test_multiple_duplicate_groups(self, scanner, test_dir):
        """测试多组重复文件"""
        create_file(test_dir / "a1.txt", b"group a")
        create_file(test_dir / "a2.txt", b"group a")
        create_file(test_dir / "b1.dat", b"group b content")
        create_file(test_dir / "b2.dat", b"group b content")

        result = scanner.scan(str(test_dir))
        assert len(result.duplicates) == 2

    def test_recursive_scan(self, scanner, test_dir):
        """测试递归扫描"""
        content = b"same"
        create_file(test_dir / "file1.txt", content)
        create_file(test_dir / "sub" / "file2.txt", content)

        result = scanner.scan(str(test_dir), recursive=True)
        assert len(result.duplicates) == 1

    def test_non_recursive_scan(self, scanner, test_dir):
        """测试非递归扫描"""
        content = b"same"
        create_file(test_dir / "file1.txt", content)
        create_file(test_dir / "sub" / "file2.txt", content)

        result = scanner.scan(str(test_dir), recursive=False)
        assert len(result.duplicates) == 0

    def test_min_size_filter(self, scanner, test_dir):
        """测试最小文件大小过滤"""
        create_file(test_dir / "small1.txt", b"ab")
        create_file(test_dir / "small2.txt", b"ab")
        create_file(test_dir / "large1.txt", b"larger content here")
        create_file(test_dir / "large2.txt", b"larger content here")

        result = scanner.scan(str(test_dir), min_size=10)
        # 小文件被过滤，只检测到大文件重复
        assert len(result.duplicates) == 1

    def test_extension_filter(self, scanner, test_dir):
        """测试文件扩展名过滤"""
        create_file(test_dir / "a.txt", b"content")
        create_file(test_dir / "b.txt", b"content")
        create_file(test_dir / "a.jpg", b"content")
        create_file(test_dir / "b.jpg", b"content")

        result = scanner.scan(str(test_dir), file_extensions=[".txt"])
        assert len(result.duplicates) == 1
        # 只检测 txt 文件
        for _, files, _ in result.duplicates:
            for f in files:
                assert f.endswith(".txt")

    def test_directory_not_found(self, scanner):
        """测试目录不存在"""
        with pytest.raises(FileNotFoundError):
            scanner.scan("/nonexistent/path")

    def test_cancel_flag(self, scanner, test_dir):
        """测试取消标志"""
        # 创建文件
        for i in range(10):
            create_file(test_dir / f"file{i}.txt", f"content {i}".encode())

        # 设置取消标志
        scanner.cancel()
        assert scanner.is_cancelled() is True

        # 重置后可以正常扫描
        scanner.reset_cancel()
        assert scanner.is_cancelled() is False

        result = scanner.scan(str(test_dir))
        assert result.cancelled is False

    def test_progress_callback(self, scanner, test_dir):
        """测试进度回调"""
        create_file(test_dir / "a.txt", b"content")
        create_file(test_dir / "b.txt", b"content")

        progress_calls = []

        def callback(status, current, total):
            progress_calls.append((status, current, total))

        scanner.scan(str(test_dir), progress_callback=callback)
        assert len(progress_calls) > 0

    def test_result_sorted_by_size(self, scanner, test_dir):
        """测试结果按大小降序排序"""
        create_file(test_dir / "small1.txt", b"small")
        create_file(test_dir / "small2.txt", b"small")
        create_file(test_dir / "large1.txt", b"larger content here!!")
        create_file(test_dir / "large2.txt", b"larger content here!!")

        result = scanner.scan(str(test_dir))
        if len(result.duplicates) >= 2:
            sizes = [size for _, _, size in result.duplicates]
            assert sizes == sorted(sizes, reverse=True)

    def test_large_files(self, scanner, test_dir):
        """测试大文件扫描"""
        content = b"x" * (1024 * 100)  # 100KB
        create_file(test_dir / "big1.bin", content)
        create_file(test_dir / "big2.bin", content)

        result = scanner.scan(str(test_dir))
        assert len(result.duplicates) == 1
        assert result.total_wasted == len(content)


class TestScanResult:
    """ScanResult 数据类测试"""

    def test_default_values(self):
        """测试默认值"""
        result = ScanResult()
        assert result.duplicates == []
        assert result.total_scanned == 0
        assert result.total_duplicates == 0
        assert result.total_wasted == 0
        assert result.cancelled is False

    def test_custom_values(self):
        """测试自定义值"""
        result = ScanResult(
            duplicates=[("hash1", ["a", "b"], 100)],
            total_scanned=10,
            total_duplicates=2,
            total_wasted=100
        )
        assert len(result.duplicates) == 1
        assert result.total_scanned == 10
