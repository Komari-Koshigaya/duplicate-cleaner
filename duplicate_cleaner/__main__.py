"""
包入口模块

支持通过 python -m duplicate_cleaner 启动 GUI。
"""

import os
import sys
import argparse

from . import __version__


def _check_single_instance() -> bool:
    """
    检查是否已有实例在运行

    Returns:
        True 如果已有实例在运行
    """
    from .utils import get_lock_file, get_config_file
    from .config import AppConfig

    # 检查配置是否启用单实例模式
    config = AppConfig.load()
    if not config.single_instance:
        return False

    lock_file = get_lock_file()

    if not lock_file.exists():
        return False

    try:
        pid = int(lock_file.read_text().strip())
        # 检查进程是否还在运行
        if sys.platform == 'win32':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if handle:
                kernel32.CloseHandle(handle)
                return True
        else:
            os.kill(pid, 0)
            return True
    except (ValueError, OSError, ProcessLookupError):
        pass

    # 进程不在运行，删除旧锁文件
    try:
        lock_file.unlink()
    except OSError:
        pass

    return False


def _activate_existing_window():
    """激活已存在的窗口"""
    if sys.platform != 'win32':
        return

    try:
        import ctypes
        from ctypes import wintypes

        EnumWindows = ctypes.windll.user32.EnumWindows
        GetWindowTextW = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible
        SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
        ShowWindow = ctypes.windll.user32.ShowWindow

        SW_RESTORE = 9
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.POINTER(ctypes.Structure))

        def callback(hwnd, _):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    if "Duplicate Cleaner" in buf.value:
                        ShowWindow(hwnd, SW_RESTORE)
                        SetForegroundWindow(hwnd)
                        return False
            return True

        EnumWindows(WNDENUMPROC(callback), None)
    except Exception:
        pass


def _write_lock_file():
    """写入锁文件"""
    from .utils import get_lock_file

    lock_file = get_lock_file()
    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(str(os.getpid()))
    except OSError:
        pass


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
        # GUI 模式 - 检查单实例
        if _check_single_instance():
            _activate_existing_window()
            return

        # 写入锁文件
        _write_lock_file()

        from .gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
