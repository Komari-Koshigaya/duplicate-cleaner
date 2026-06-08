"""
Windows 右键菜单集成模块

通过 Windows 注册表为资源管理器添加右键菜单项，支持：
- 右键目录直接扫描
- 右键目录进行文件夹对比
- 从菜单中移除集成

操作 HKEY_CURRENT_USER，无需管理员权限。
"""

import logging
import sys
from typing import Optional

logger = logging.getLogger("duplicate_cleaner")

# 注册表路径
_DIR_SHELL_KEY = r"Software\Classes\Directory\shell\DuplicateCleaner"
_BG_SHELL_KEY = r"Software\Classes\Directory\Background\shell\DuplicateCleaner"

# 菜单配置
_MENU_LABEL = "用 Duplicate Cleaner 扫描(&D)"
_COMPARE_LABEL = "与另一个文件夹对比...(&C)"


def _get_exe_command() -> Optional[str]:
    """
    获取可执行命令路径

    Returns:
        命令字符串，失败返回 None
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包的 exe
        return f'"{sys.executable}"'
    else:
        # 开发模式：python -m duplicate_cleaner
        return f'"{sys.executable}" -m duplicate_cleaner'


def _create_registry_tree(key_path: str, exe_cmd: str) -> bool:
    """
    创建注册表菜单树

    Args:
        key_path: 根键路径
        exe_cmd: 可执行命令

    Returns:
        是否成功
    """
    try:
        import winreg

        # 根键：菜单标签和图标
        root_key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(root_key, "", 0, winreg.REG_SZ, _MENU_LABEL)
        winreg.SetValueEx(root_key, "Icon", 0, winreg.REG_SZ, exe_cmd.strip('"'))
        winreg.CloseKey(root_key)

        # 扫描命令
        cmd_key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path + r"\command")
        winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, f'{exe_cmd} "%V"')
        winreg.CloseKey(cmd_key)

        # 对比子菜单
        compare_key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path + r"\subshell\Compare")
        winreg.SetValueEx(compare_key, "", 0, winreg.REG_SZ, _COMPARE_LABEL)
        winreg.CloseKey(compare_key)

        # 对比命令
        compare_cmd = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path + r"\subshell\Compare\command")
        winreg.SetValueEx(compare_cmd, "", 0, winreg.REG_SZ, f'{exe_cmd} --compare "%V"')
        winreg.CloseKey(compare_cmd)

        return True

    except Exception as e:
        logger.error(f"创建注册表项失败 ({key_path}): {e}")
        return False


def _delete_registry_tree(key_path: str) -> bool:
    """
    递归删除注册表键树

    Args:
        key_path: 根键路径

    Returns:
        是否成功
    """
    try:
        import winreg

        def _delete_subkeys(base_key, subkey_path):
            """递归删除子键"""
            try:
                key = winreg.OpenKey(base_key, subkey_path)
            except FileNotFoundError:
                return

            # 枚举并删除所有子键
            subkeys = []
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                    subkeys.append(name)
                    i += 1
                except OSError:
                    break

            for subkey in subkeys:
                _delete_subkeys(base_key, subkey_path + "\\" + subkey)

            winreg.CloseKey(key)
            winreg.DeleteKey(base_key, subkey_path)

        _delete_subkeys(winreg.HKEY_CURRENT_USER, key_path)
        return True

    except FileNotFoundError:
        return True  # 已不存在也算成功
    except Exception as e:
        logger.error(f"删除注册表项失败 ({key_path}): {e}")
        return False


def is_shell_integration_enabled() -> bool:
    """
    检查右键菜单是否已集成

    Returns:
        是否已启用
    """
    try:
        import winreg
        # 检查目录右键菜单是否存在
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, _DIR_SHELL_KEY + r"\command")
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def enable_shell_integration() -> bool:
    """
    添加右键菜单项

    Returns:
        是否成功
    """
    exe_cmd = _get_exe_command()
    if not exe_cmd:
        logger.error("无法获取可执行文件路径")
        return False

    ok1 = _create_registry_tree(_DIR_SHELL_KEY, exe_cmd)
    ok2 = _create_registry_tree(_BG_SHELL_KEY, exe_cmd)

    if ok1 and ok2:
        logger.info("右键菜单已启用")
        return True
    else:
        logger.warning("右键菜单部分启用失败")
        return False


def disable_shell_integration() -> bool:
    """
    移除右键菜单项

    Returns:
        是否成功
    """
    ok1 = _delete_registry_tree(_DIR_SHELL_KEY)
    ok2 = _delete_registry_tree(_BG_SHELL_KEY)

    if ok1 and ok2:
        logger.info("右键菜单已移除")
        return True
    else:
        logger.warning("右键菜单移除部分失败")
        return False
