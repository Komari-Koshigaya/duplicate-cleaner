#!/usr/bin/env python3
"""
重复文件查找与清理工具
通过文件内容哈希判断重复，支持交互式确认和一键删除
"""

import os
import sys
import hashlib
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def format_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def get_file_hash(filepath: str, chunk_size: int = 8192) -> str:
    """计算文件的 MD5 哈希值（分块读取，支持大文件）"""
    md5 = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                md5.update(chunk)
        return md5.hexdigest()
    except (PermissionError, OSError):
        return None


def scan_directory(directory: str, recursive: bool = True) -> Dict[int, List[str]]:
    """
    扫描目录，按文件大小分组
    返回: {size: [filepath1, filepath2, ...]}
    """
    size_groups = defaultdict(list)
    base_path = Path(directory)

    if recursive:
        pattern = '**/*'
    else:
        pattern = '*'

    for item in base_path.glob(pattern):
        if item.is_file():
            try:
                size = item.stat().st_size
                size_groups[size].append(str(item))
            except (PermissionError, OSError):
                continue

    return size_groups


def find_duplicates(directory: str, recursive: bool = True, min_size: int = 1) -> List[Tuple[str, List[str]]]:
    """
    查找重复文件
    返回: [(hash, [filepath1, filepath2, ...]), ...]
    """
    print(f"\n🔍 扫描目录: {directory}")
    print(f"   递归扫描: {'是' if recursive else '否'}")
    print(f"   最小文件大小: {format_size(min_size)}")

    # 第一步：按文件大小分组
    size_groups = scan_directory(directory, recursive)

    # 过滤掉小于 min_size 的文件和只有一个文件的组
    candidate_groups = {
        size: files for size, files in size_groups.items()
        if size >= min_size and len(files) > 1
    }

    if not candidate_groups:
        print("\n✅ 未发现重复文件")
        return []

    total_candidates = sum(len(files) for files in candidate_groups.values())
    print(f"\n📊 发现 {total_candidates} 个可能重复的文件（按大小分组）")

    # 第二步：计算哈希
    hash_groups = defaultdict(list)
    processed = 0

    for size, files in candidate_groups.items():
        for filepath in files:
            processed += 1
            if processed % 10 == 0 or processed == total_candidates:
                print(f"\r   计算哈希: {processed}/{total_candidates}", end="", flush=True)

            file_hash = get_file_hash(filepath)
            if file_hash:
                hash_groups[file_hash].append(filepath)

    print()  # 换行

    # 过滤出真正重复的文件
    duplicates = [
        (hash_val, files) for hash_val, files in hash_groups.items()
        if len(files) > 1
    ]

    return duplicates


def display_duplicates(duplicates: List[Tuple[str, List[str]]]) -> int:
    """显示重复文件列表，返回重复文件总数"""
    if not duplicates:
        print("\n✅ 未发现重复文件")
        return 0

    total_duplicates = 0
    total_wasted = 0

    print("\n" + "=" * 60)
    print("📋 发现以下重复文件:")
    print("=" * 60)

    for i, (file_hash, files) in enumerate(duplicates, 1):
        file_size = os.path.getsize(files[0])
        wasted = file_size * (len(files) - 1)
        total_wasted += wasted
        total_duplicates += len(files) - 1

        print(f"\n📁 重复组 #{i}")
        print(f"   哈希: {file_hash[:16]}...")
        print(f"   文件大小: {format_size(file_size)}")
        print(f"   浪费空间: {format_size(wasted)}")
        print(f"   文件列表:")

        for j, filepath in enumerate(files, 1):
            print(f"      [{j}] {filepath}")

    print("\n" + "=" * 60)
    print(f"📊 统计: 共 {len(duplicates)} 组重复，{total_duplicates} 个重复文件")
    print(f"💾 浪费空间: {format_size(total_wasted)}")
    print("=" * 60)

    return total_duplicates


def interactive_clean(duplicates: List[Tuple[str, List[str]]]) -> List[str]:
    """交互式清理重复文件，返回要删除的文件列表"""
    files_to_delete = []

    print("\n" + "=" * 60)
    print("🗑️  交互式清理模式")
    print("=" * 60)
    print("操作说明:")
    print("  - 输入文件编号保留该文件，删除其他")
    print("  - 输入 's' 跳过当前组")
    print("  - 输入 'q' 退出清理")
    print("  - 输入 'a' 删除每组中的多余文件（保留第一个）")
    print("=" * 60)

    auto_mode = False

    for i, (file_hash, files) in enumerate(duplicates, 1):
        file_size = os.path.getsize(files[0])

        print(f"\n📁 重复组 #{i}/{len(duplicates)}")
        print(f"   文件大小: {format_size(file_size)}")

        for j, filepath in enumerate(files, 1):
            print(f"   [{j}] {filepath}")

        if auto_mode:
            # 自动模式：保留第一个，删除其余
            files_to_delete.extend(files[1:])
            print(f"   → 自动保留 [1]，删除其余 {len(files)-1} 个文件")
            continue

        while True:
            choice = input("\n   请输入选择: ").strip().lower()

            if choice == 'q':
                print("\n⏹️  退出清理模式")
                return files_to_delete

            if choice == 's':
                print("   ⏭️  跳过此组")
                break

            if choice == 'a':
                auto_mode = True
                files_to_delete.extend(files[1:])
                print(f"   → 保留 [1]，删除其余 {len(files)-1} 个文件")
                print("   ℹ️  已切换到自动模式，后续将自动处理")
                break

            try:
                idx = int(choice)
                if 1 <= idx <= len(files):
                    # 保留选择的文件，删除其他
                    keep_file = files[idx - 1]
                    to_delete = [f for f in files if f != keep_file]
                    files_to_delete.extend(to_delete)
                    print(f"   → 保留 [{idx}]，删除 {len(to_delete)} 个文件")
                    break
                else:
                    print(f"   ❌ 请输入 1-{len(files)} 之间的数字")
            except ValueError:
                print("   ❌ 无效输入，请重试")

    return files_to_delete


def delete_files(files: List[str], dry_run: bool = False) -> Tuple[int, int]:
    """删除文件，返回 (成功数, 失败数)"""
    if not files:
        return 0, 0

    success = 0
    failed = 0

    print("\n" + "=" * 60)
    if dry_run:
        print("🔍 预览模式 - 以下文件将被删除（未实际删除）:")
    else:
        print("🗑️  正在删除文件...")
    print("=" * 60)

    for filepath in files:
        try:
            if dry_run:
                print(f"   [预览] {filepath}")
                success += 1
            else:
                os.remove(filepath)
                print(f"   [已删除] {filepath}")
                success += 1
        except (PermissionError, OSError) as e:
            print(f"   [失败] {filepath}: {e}")
            failed += 1

    return success, failed


def main():
    parser = argparse.ArgumentParser(
        description="重复文件查找与清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s /path/to/directory          # 扫描并交互式清理
  %(prog)s -r /path/to/directory        # 递归扫描子目录
  %(prog)s --dry-run /path/to/directory # 预览模式，不实际删除
  %(prog)s --auto /path/to/directory    # 自动模式，保留每组第一个
  %(prog)s --min-size 1024 /path/to/directory  # 只检查大于1KB的文件
        """
    )

    parser.add_argument(
        "directory",
        help="要扫描的目录路径"
    )

    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        default=True,
        help="递归扫描子目录（默认开启）"
    )

    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="不递归扫描子目录"
    )

    parser.add_argument(
        "--min-size",
        type=int,
        default=1,
        help="最小文件大小（字节），默认 1"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，显示将删除的文件但不实际删除"
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="自动模式，保留每组第一个文件，删除其余"
    )

    parser.add_argument(
        "--list-only",
        action="store_true",
        help="仅列出重复文件，不进行删除操作"
    )

    args = parser.parse_args()

    # 验证目录
    if not os.path.isdir(args.directory):
        print(f"❌ 错误: 目录不存在: {args.directory}")
        sys.exit(1)

    recursive = not args.no_recursive

    # 查找重复文件
    duplicates = find_duplicates(args.directory, recursive, args.min_size)

    # 显示重复文件
    total = display_duplicates(duplicates)

    if total == 0:
        sys.exit(0)

    # 如果只是列出，到此结束
    if args.list_only:
        sys.exit(0)

    # 确定要删除的文件
    files_to_delete = []

    if args.auto:
        # 自动模式
        for file_hash, files in duplicates:
            files_to_delete.extend(files[1:])  # 保留第一个，删除其余
        print(f"\n🤖 自动模式: 将保留每组第一个文件，删除 {len(files_to_delete)} 个重复文件")
    else:
        # 交互模式
        files_to_delete = interactive_clean(duplicates)

    if not files_to_delete:
        print("\n✅ 没有需要删除的文件")
        sys.exit(0)

    # 执行删除
    if args.dry_run:
        print(f"\n📋 预览: 将删除 {len(files_to_delete)} 个文件")
        delete_files(files_to_delete, dry_run=True)
    else:
        # 最终确认
        print(f"\n⚠️  即将删除 {len(files_to_delete)} 个文件")
        confirm = input("确认删除? (输入 'yes' 确认): ").strip().lower()

        if confirm == 'yes':
            success, failed = delete_files(files_to_delete)
            print(f"\n✅ 完成: 成功 {success} 个，失败 {failed} 个")
        else:
            print("\n⏹️  已取消删除操作")


if __name__ == "__main__":
    main()
