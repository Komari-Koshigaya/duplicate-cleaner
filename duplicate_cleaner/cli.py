"""
命令行界面模块

提供命令行模式的重复文件查找和清理功能。
复用 scanner 模块的扫描引擎。
"""

import os
import sys
import argparse
import logging
from pathlib import Path

from . import __version__
from .scanner import FileScanner, ScanResult
from .utils import format_size, is_send2trash_available, setup_logging

logger = logging.getLogger("duplicate_cleaner")


def display_duplicates(result: ScanResult) -> None:
    """
    在终端显示重复文件列表

    Args:
        result: 扫描结果
    """
    if not result.duplicates:
        print("\n✅ 未发现重复文件")
        return

    print("\n" + "=" * 60)
    print("📋 发现以下重复文件:")
    print("=" * 60)

    for i, (file_hash, files, size) in enumerate(result.duplicates, 1):
        wasted = size * (len(files) - 1)

        print(f"\n📁 重复组 #{i}")
        print(f"   哈希: {file_hash[:16]}...")
        print(f"   文件大小: {format_size(size)}")
        print(f"   浪费空间: {format_size(wasted)}")
        print(f"   文件列表:")

        for j, filepath in enumerate(files, 1):
            print(f"      [{j}] {filepath}")

    print("\n" + "=" * 60)
    print(f"📊 统计: 共 {len(result.duplicates)} 组重复，"
          f"{result.total_duplicates} 个重复文件")
    print(f"💾 浪费空间: {format_size(result.total_wasted)}")
    print("=" * 60)


def interactive_clean(result: ScanResult) -> list:
    """
    交互式选择要删除的文件

    Args:
        result: 扫描结果

    Returns:
        要删除的文件路径列表
    """
    files_to_delete = []

    print("\n" + "=" * 60)
    print("🗑️  交互式清理模式")
    print("=" * 60)
    print("操作说明:")
    print("  - 输入文件编号保留该文件，删除其他")
    print("  - 输入 's' 跳过当前组")
    print("  - 输入 'q' 退出清理")
    print("  - 输入 'a' 自动处理（保留每组第一个）")
    print("=" * 60)

    auto_mode = False

    for i, (file_hash, files, size) in enumerate(result.duplicates, 1):
        print(f"\n📁 重复组 #{i}/{len(result.duplicates)}")
        print(f"   文件大小: {format_size(size)}")

        for j, filepath in enumerate(files, 1):
            print(f"   [{j}] {filepath}")

        if auto_mode:
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
                print("   ℹ️  已切换到自动模式")
                break

            try:
                idx = int(choice)
                if 1 <= idx <= len(files):
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


def delete_files(files: list, use_trash: bool = False, dry_run: bool = False) -> tuple:
    """
    删除文件

    Args:
        files: 要删除的文件路径列表
        use_trash: 是否移到回收站
        dry_run: 是否只预览不实际删除

    Returns:
        (success_count, fail_count)
    """
    if not files:
        return 0, 0

    success = 0
    failed = 0

    print("\n" + "=" * 60)
    if dry_run:
        print("🔍 预览模式 - 以下文件将被删除:")
    elif use_trash:
        print("🗑️  正在移到回收站...")
    else:
        print("🗑️  正在永久删除...")
    print("=" * 60)

    for filepath in files:
        try:
            if dry_run:
                print(f"   [预览] {filepath}")
                success += 1
            elif use_trash:
                import send2trash
                send2trash.send2trash(filepath)
                print(f"   [已移到回收站] {filepath}")
                success += 1
            else:
                os.remove(filepath)
                print(f"   [已删除] {filepath}")
                success += 1
        except Exception as e:
            print(f"   [失败] {filepath}: {e}")
            failed += 1

    return success, failed


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="duplicate-cleaner",
        description="重复文件查找与清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s /path/to/directory              # 扫描并交互式清理
  %(prog)s --dry-run /path/to/directory    # 预览模式
  %(prog)s --auto /path/to/directory       # 自动模式
  %(prog)s --trash /path/to/directory      # 移到回收站
  %(prog)s --min-size 1024 /path/to/dir    # 只检查大于1KB的文件
        """
    )

    parser.add_argument("directory", help="要扫描的目录路径")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-r", "--recursive", action="store_true", default=True, help="递归扫描子目录（默认）")
    parser.add_argument("--no-recursive", action="store_true", help="不递归扫描子目录")
    parser.add_argument("--min-size", type=int, default=0, help="最小文件大小（字节）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际删除")
    parser.add_argument("--auto", action="store_true", help="自动模式，保留每组第一个")
    parser.add_argument("--trash", action="store_true", help="移到回收站而非永久删除")
    parser.add_argument("--list-only", action="store_true", help="仅列出重复文件")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 配置日志
    if args.verbose:
        setup_logging(level=logging.DEBUG)

    # 验证目录
    if not os.path.isdir(args.directory):
        print(f"❌ 错误: 目录不存在: {args.directory}")
        sys.exit(1)

    # 检查 send2trash
    if args.trash and not is_send2trash_available():
        print("❌ 错误: --trash 需要安装 send2trash")
        print("   运行: pip install send2trash")
        sys.exit(1)

    # 扫描
    print(f"\n🔍 扫描目录: {args.directory}")
    recursive = not args.no_recursive

    scanner = FileScanner()

    def progress(status, current, total):
        if total > 0:
            print(f"\r   {status}", end="", flush=True)

    result = scanner.scan(
        directory=args.directory,
        recursive=recursive,
        min_size=args.min_size,
        progress_callback=progress
    )

    print()  # 换行

    if result.cancelled:
        print("\n⏹️  扫描已取消")
        sys.exit(0)

    # 显示结果
    display_duplicates(result)

    if not result.duplicates or args.list_only:
        sys.exit(0)

    # 清理
    if args.auto:
        files_to_delete = []
        for _, files, _ in result.duplicates:
            files_to_delete.extend(files[1:])
        print(f"\n🤖 自动模式: 将删除 {len(files_to_delete)} 个重复文件")
    else:
        files_to_delete = interactive_clean(result)

    if not files_to_delete:
        print("\n✅ 没有需要删除的文件")
        sys.exit(0)

    # 执行删除
    if args.dry_run:
        print(f"\n📋 预览: 将删除 {len(files_to_delete)} 个文件")
        delete_files(files_to_delete, dry_run=True)
    else:
        print(f"\n⚠️  即将删除 {len(files_to_delete)} 个文件")
        confirm = input("确认删除? (输入 'yes' 确认): ").strip().lower()
        if confirm == 'yes':
            success, failed = delete_files(files_to_delete, use_trash=args.trash)
            print(f"\n✅ 完成: 成功 {success} 个，失败 {failed} 个")
        else:
            print("\n⏹️  已取消删除操作")


if __name__ == "__main__":
    main()
