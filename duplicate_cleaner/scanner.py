"""
扫描引擎模块

负责文件收集、哈希计算、重复检测等核心逻辑。
与 UI 完全解耦，可独立测试。

核心算法：
1. 按文件大小分组（大小不同的文件不可能重复）
2. 快速哈希（读取文件头部 64KB）进一步筛选
3. 对可疑文件计算完整 MD5 哈希确认
4. 多线程并行计算提升性能（自适应硬盘类型）
"""

import os
import sys
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from dataclasses import dataclass, field
import threading

logger = logging.getLogger("duplicate_cleaner")

# 快速哈希读取大小（64KB），用于第一轮筛选
QUICK_HASH_SIZE = 65536

# 完整哈希读取块大小（128KB）
FULL_HASH_CHUNK_SIZE = 131072

# 默认线程数配置
DEFAULT_QUICK_HASH_WORKERS = 8
DEFAULT_FULL_HASH_WORKERS = 4


def detect_disk_type(path: str) -> str:
    """
    检测路径所在硬盘的类型

    Args:
        path: 文件或目录路径

    Returns:
        "ssd" - 固态硬盘
        "hdd" - 机械硬盘
        "unknown" - 未知
    """
    try:
        if sys.platform == 'win32':
            # Windows: 使用 fsutil 命令检测
            # 获取盘符
            drive = Path(path).drive or "C:"
            drive_letter = drive[0]

            # 尝试通过 PowerShell 检测
            try:
                cmd = f'powershell -Command "Get-PhysicalDisk | Where-Object {{$_.DeviceID -eq (Get-Partition -DriveLetter {drive_letter}).DiskNumber}} | Select-Object -ExpandProperty MediaType"'
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                media_type = result.stdout.strip().lower()
                if "ssd" in media_type or "solid" in media_type:
                    return "ssd"
                elif "hdd" in media_type or "hard" in media_type:
                    return "hdd"
            except Exception:
                pass

            # 备用方案：通过随机读取性能测试
            return _benchmark_disk(path)

        elif sys.platform == 'darwin':
            # macOS: 检查是否为 SSD
            try:
                result = subprocess.run(
                    ['diskutil', 'info', path],
                    capture_output=True, text=True, timeout=5
                )
                if "Solid State" in result.stdout:
                    return "ssd"
                elif "Rotational" in result.stdout:
                    return "hdd"
            except Exception:
                pass

        else:
            # Linux: 检查 /sys/block/*/queue/rotational
            try:
                # 获取设备名
                result = subprocess.run(
                    ['df', '--output=source', path],
                    capture_output=True, text=True, timeout=5
                )
                device = result.stdout.strip().split('\n')[-1].strip()
                device_name = device.split('/')[-1].rstrip('0123456789')

                rotational_path = f"/sys/block/{device_name}/queue/rotational"
                if os.path.exists(rotational_path):
                    with open(rotational_path, 'r') as f:
                        rotational = f.read().strip()
                    return "hdd" if rotational == "1" else "ssd"
            except Exception:
                pass

    except Exception as e:
        logger.debug(f"硬盘类型检测失败: {e}")

    return "unknown"


def _benchmark_disk(path: str) -> str:
    """
    通过简单的读取性能测试判断硬盘类型

    Args:
        path: 测试路径

    Returns:
        "ssd" 或 "hdd"
    """
    import time
    import tempfile

    try:
        # 创建临时文件进行测试
        test_dir = Path(path) if Path(path).is_dir() else Path(path).parent
        test_file = test_dir / ".disk_benchmark_test"

        # 写入测试数据
        data = os.urandom(1024 * 1024)  # 1MB
        with open(test_file, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # 随机读取测试
        start = time.time()
        with open(test_file, 'rb') as f:
            for _ in range(100):
                pos = (hash(str(time.time())) % 1000) * 1024
                f.seek(pos)
                f.read(1024)
        elapsed = time.time() - start

        # 清理
        try:
            test_file.unlink()
        except Exception:
            pass

        # SSD 通常在 0.1 秒内完成，HDD 可能需要 0.5 秒以上
        return "ssd" if elapsed < 0.2 else "hdd"

    except Exception:
        return "unknown"


def get_optimal_workers(path: str, operation: str = "quick_hash") -> int:
    """
    根据硬盘类型获取最优线程数

    Args:
        path: 扫描路径
        operation: 操作类型 "quick_hash" 或 "full_hash"

    Returns:
        推荐的线程数
    """
    disk_type = detect_disk_type(path)
    cpu_count = os.cpu_count() or 4

    if operation == "quick_hash":
        # 快速哈希：IO 密集型，可以更多并发
        if disk_type == "ssd":
            # SSD: 可以高并发
            return min(cpu_count * 2, 16)
        elif disk_type == "hdd":
            # HDD: 减少并发，避免磁头寻道
            return min(4, cpu_count)
        else:
            # 未知：保守估计
            return min(8, cpu_count)
    else:
        # 完整哈希：CPU 和 IO 混合
        if disk_type == "ssd":
            return min(cpu_count, 8)
        elif disk_type == "hdd":
            return min(2, cpu_count)
        else:
            return min(4, cpu_count)


@dataclass
class ScanResult:
    """
    扫描结果数据类

    Attributes:
        duplicates: 重复文件组列表，每组为 (hash, [file_paths], file_size)
        total_scanned: 扫描的文件总数
        total_duplicates: 重复文件总数
        total_wasted: 浪费的磁盘空间（字节）
        cancelled: 是否被用户取消
    """
    duplicates: List[Tuple[str, List[str], int]] = field(default_factory=list)
    total_scanned: int = 0
    total_duplicates: int = 0
    total_wasted: int = 0
    cancelled: bool = False


class FileScanner:
    """
    文件扫描器

    负责扫描目录、计算哈希、检测重复文件。
    线程安全：所有公共方法可在任意线程调用。

    使用示例：
        scanner = FileScanner()
        result = scanner.scan("/path/to/dir", recursive=True)
        for hash_val, files, size in result.duplicates:
            print(f"重复组: {files}")
    """

    def __init__(self, max_workers: Optional[int] = None):
        """
        初始化扫描器

        Args:
            max_workers: 最大线程数，None 则自动根据硬盘类型调整
        """
        # 线程数会在扫描时根据硬盘类型自适应调整
        self._max_workers = max_workers
        # 取消标志，线程安全
        self._cancel_flag = False
        # 锁：保护共享状态
        self._lock = threading.Lock()
        # 检测到的硬盘类型
        self._disk_type = "unknown"

    def cancel(self) -> None:
        """
        请求取消正在进行的扫描

        线程安全，可在任意线程调用。
        """
        with self._lock:
            self._cancel_flag = True

    def reset_cancel(self) -> None:
        """重置取消标志，准备新的扫描"""
        with self._lock:
            self._cancel_flag = False

    def is_cancelled(self) -> bool:
        """检查是否已被取消"""
        with self._lock:
            return self._cancel_flag

    def scan(
        self,
        directory: str,
        recursive: bool = True,
        min_size: int = 0,
        file_extensions: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> ScanResult:
        """
        扫描目录查找重复文件

        Args:
            directory: 要扫描的目录路径
            recursive: 是否递归扫描子目录
            min_size: 最小文件大小（字节），忽略小于此大小的文件
            file_extensions: 文件扩展名过滤列表，如 ['.jpg', '.png']，None 表示不过滤
            progress_callback: 进度回调函数 callback(status, current, total)

        Returns:
            ScanResult 扫描结果

        Raises:
            FileNotFoundError: 目录不存在
            PermissionError: 无权限访问目录
        """
        self.reset_cancel()
        result = ScanResult()

        directory_path = Path(directory)
        if not directory_path.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")
        if not directory_path.is_dir():
            raise FileNotFoundError(f"不是有效目录: {directory}")

        # 检测硬盘类型并获取最优线程数
        if self._max_workers is None:
            self._disk_type = detect_disk_type(directory)
            quick_workers = get_optimal_workers(directory, "quick_hash")
            full_workers = get_optimal_workers(directory, "full_hash")
            logger.info(f"硬盘类型: {self._disk_type}, 快速哈希线程数: {quick_workers}, 完整哈希线程数: {full_workers}")
        else:
            quick_workers = self._max_workers
            full_workers = min(self._max_workers, 4)

        # === 第一阶段：收集文件并按大小分组 ===
        logger.info(f"开始扫描目录: {directory}")
        if progress_callback:
            progress_callback("正在扫描文件...", 0, 0)

        size_groups = self._collect_files(directory_path, recursive, min_size, file_extensions)
        result.total_scanned = sum(len(files) for files in size_groups.values())
        logger.info(f"扫描到 {result.total_scanned} 个文件")

        if self.is_cancelled():
            result.cancelled = True
            return result

        # 只保留有重复可能的文件（大小相同的文件）
        candidates = []
        for size, files in size_groups.items():
            if len(files) > 1:
                candidates.extend(files)

        if not candidates:
            logger.info("未发现可能重复的文件")
            return result

        logger.info(f"发现 {len(candidates)} 个可能重复的文件（按大小筛选）")

        # === 第二阶段：快速哈希（读取文件头部） ===
        if progress_callback:
            progress_callback("正在计算快速哈希...", 0, len(candidates))

        quick_hash_groups = self._compute_quick_hashes(candidates, progress_callback, quick_workers)

        if self.is_cancelled():
            result.cancelled = True
            return result

        # 只对快速哈希相同的文件计算完整哈希
        full_hash_candidates = []
        for hash_val, files in quick_hash_groups.items():
            if len(files) > 1:
                full_hash_candidates.extend(files)

        if not full_hash_candidates:
            logger.info("快速哈希阶段未发现重复文件")
            return result

        logger.info(f"快速哈希发现 {len(full_hash_candidates)} 个可疑文件，开始精确验证")

        # === 第三阶段：完整哈希验证 ===
        if progress_callback:
            progress_callback("正在精确验证...", 0, len(full_hash_candidates))

        full_hash_groups = self._compute_full_hashes(full_hash_candidates, progress_callback, full_workers)

        if self.is_cancelled():
            result.cancelled = True
            return result

        # === 第四阶段：整理结果 ===
        for hash_val, files_info in full_hash_groups.items():
            if len(files_info) > 1:
                files = [f[0] for f in files_info]
                size = files_info[0][1]
                result.duplicates.append((hash_val, files, size))

        # 按文件大小降序排序
        result.duplicates.sort(key=lambda x: x[2], reverse=True)

        # 计算统计信息
        result.total_duplicates = sum(len(files) for _, files, _ in result.duplicates)
        result.total_wasted = sum(size * (len(files) - 1) for _, files, size in result.duplicates)

        logger.info(f"扫描完成: {len(result.duplicates)} 组重复，"
                    f"{result.total_duplicates} 个文件，"
                    f"浪费 {result.total_wasted} 字节")

        return result

    def _collect_files(
        self,
        base_path: Path,
        recursive: bool,
        min_size: int,
        file_extensions: Optional[List[str]]
    ) -> Dict[int, List[str]]:
        """
        收集目录中的文件并按大小分组

        Args:
            base_path: 基础目录
            recursive: 是否递归
            min_size: 最小文件大小
            file_extensions: 扩展名过滤

        Returns:
            {file_size: [file_path, ...]} 字典
        """
        size_groups: Dict[int, List[str]] = defaultdict(list)
        pattern = '**/*' if recursive else '*'

        for item in base_path.glob(pattern):
            if self.is_cancelled():
                break

            if not item.is_file():
                continue

            # 扩展名过滤
            if file_extensions and item.suffix.lower() not in file_extensions:
                continue

            try:
                # 使用 lstat 避免跟随符号链接
                stat = item.lstat()
                # 跳过符号链接和空文件
                if stat.st_size >= min_size and stat.st_size > 0:
                    size_groups[stat.st_size].append(str(item))
            except (PermissionError, OSError) as e:
                logger.warning(f"无法访问文件: {item} - {e}")
                continue

        return size_groups

    def _compute_quick_hashes(
        self,
        files: List[str],
        progress_callback: Optional[Callable] = None,
        max_workers: int = DEFAULT_QUICK_HASH_WORKERS
    ) -> Dict[str, List[str]]:
        """
        多线程计算文件快速哈希（仅读取头部）

        Args:
            files: 文件路径列表
            progress_callback: 进度回调
            max_workers: 最大线程数

        Returns:
            {hash: [file_path, ...]} 字典
        """
        hash_groups: Dict[str, List[str]] = defaultdict(list)
        processed = 0
        total = len(files)

        def calc_quick_hash(filepath: str) -> Tuple[str, Optional[str]]:
            """计算单个文件的快速哈希"""
            try:
                with open(filepath, 'rb') as f:
                    data = f.read(QUICK_HASH_SIZE)
                return filepath, hashlib.md5(data).hexdigest()
            except (PermissionError, OSError) as e:
                logger.warning(f"快速哈希失败: {filepath} - {e}")
                return filepath, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(calc_quick_hash, f): f for f in files}

            for future in as_completed(futures):
                if self.is_cancelled():
                    # 取消未完成的任务
                    for f in futures:
                        f.cancel()
                    break

                filepath, hash_val = future.result()
                processed += 1

                if hash_val:
                    hash_groups[hash_val].append(filepath)

                # 每 50 个文件报告一次进度
                if processed % 50 == 0 or processed == total:
                    if progress_callback:
                        progress_callback(f"快速哈希: {processed}/{total}", processed, total)

        return hash_groups

    def _compute_full_hashes(
        self,
        files: List[str],
        progress_callback: Optional[Callable] = None,
        max_workers: int = DEFAULT_FULL_HASH_WORKERS
    ) -> Dict[str, List[Tuple[str, int]]]:
        """
        多线程计算文件完整 MD5 哈希

        Args:
            files: 文件路径列表
            progress_callback: 进度回调
            max_workers: 最大线程数

        Returns:
            {hash: [(file_path, file_size), ...]} 字典
        """
        hash_groups: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        processed = 0
        total = len(files)

        def calc_full_hash(filepath: str) -> Tuple[str, Optional[str]]:
            """计算单个文件的完整哈希"""
            try:
                md5 = hashlib.md5(usedforsecurity=False)
                with open(filepath, 'rb') as f:
                    while True:
                        chunk = f.read(FULL_HASH_CHUNK_SIZE)
                        if not chunk:
                            break
                        md5.update(chunk)
                return filepath, md5.hexdigest()
            except (PermissionError, OSError) as e:
                logger.warning(f"完整哈希失败: {filepath} - {e}")
                return filepath, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(calc_full_hash, f): f for f in files}

            for future in as_completed(futures):
                if self.is_cancelled():
                    for f in futures:
                        f.cancel()
                    break

                filepath, hash_val = future.result()
                processed += 1

                if hash_val:
                    try:
                        size = os.path.getsize(filepath)
                        hash_groups[hash_val].append((filepath, size))
                    except OSError:
                        pass

                if processed % 20 == 0 or processed == total:
                    if progress_callback:
                        progress_callback(f"精确验证: {processed}/{total}", processed, total)

        return hash_groups
