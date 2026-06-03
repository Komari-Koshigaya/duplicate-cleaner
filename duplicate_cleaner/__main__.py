"""
包入口模块

支持通过 python -m duplicate_cleaner 启动 GUI。
"""

import sys
import argparse

from . import __version__


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        prog="duplicate-cleaner",
        description="重复文件查找与清理工具"
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="使用命令行模式（不启动 GUI）"
    )
    parser.add_argument(
        "directory", nargs="?",
        help="要扫描的目录路径（CLI 模式）"
    )

    args = parser.parse_args()

    if args.cli or args.directory:
        # 命令行模式
        from .cli import main as cli_main
        cli_main()
    else:
        # GUI 模式
        from .gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
