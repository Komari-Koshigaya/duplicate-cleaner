"""
右键菜单集成单元测试

使用 mock 测试注册表操作，无需实际修改注册表。
"""

import sys
import pytest
from unittest.mock import patch, MagicMock, call


class TestGetExeCommand:
    """_get_exe_command 测试"""

    @patch.object(sys, 'frozen', True, create=True)
    @patch.object(sys, 'executable', r'C:\path\to\app.exe')
    def test_frozen_mode(self):
        """测试打包模式获取命令"""
        from duplicate_cleaner.shell_integration import _get_exe_command
        result = _get_exe_command()
        assert result == r'"C:\path\to\app.exe"'

    @patch.object(sys, 'frozen', False, create=True)
    @patch.object(sys, 'executable', r'C:\Python313\python.exe')
    def test_dev_mode(self):
        """测试开发模式获取命令"""
        from duplicate_cleaner.shell_integration import _get_exe_command
        result = _get_exe_command()
        assert 'python.exe' in result
        assert '-m duplicate_cleaner' in result


class TestShellIntegration:
    """右键菜单集成测试"""

    @patch('winreg.OpenKey')
    def test_is_enabled_when_exists(self, mock_open):
        """测试检测到已启用"""
        mock_open.return_value = MagicMock()

        from duplicate_cleaner.shell_integration import is_shell_integration_enabled
        assert is_shell_integration_enabled() is True

    @patch('winreg.OpenKey', side_effect=FileNotFoundError)
    def test_is_disabled_when_missing(self, mock_open):
        """测试检测到未启用"""
        from duplicate_cleaner.shell_integration import is_shell_integration_enabled
        assert is_shell_integration_enabled() is False

    @patch('duplicate_cleaner.shell_integration._get_exe_command')
    @patch('duplicate_cleaner.shell_integration._create_registry_tree')
    def test_enable_calls_create(self, mock_create, mock_cmd):
        """测试启用菜单调用创建函数"""
        mock_cmd.return_value = '"python" -m duplicate_cleaner'
        mock_create.return_value = True

        from duplicate_cleaner.shell_integration import enable_shell_integration
        result = enable_shell_integration()

        assert result is True
        assert mock_create.call_count == 2  # Directory + Background

    @patch('duplicate_cleaner.shell_integration._get_exe_command')
    def test_enable_fails_without_exe(self, mock_cmd):
        """测试获取不到命令时启用失败"""
        mock_cmd.return_value = None

        from duplicate_cleaner.shell_integration import enable_shell_integration
        result = enable_shell_integration()
        assert result is False

    @patch('duplicate_cleaner.shell_integration._delete_registry_tree')
    def test_disable_calls_delete(self, mock_delete):
        """测试禁用菜单调用删除函数"""
        mock_delete.return_value = True

        from duplicate_cleaner.shell_integration import disable_shell_integration
        result = disable_shell_integration()

        assert result is True
        assert mock_delete.call_count == 2  # Directory + Background

    @patch('duplicate_cleaner.shell_integration._delete_registry_tree')
    def test_disable_partial_failure(self, mock_delete):
        """测试部分删除失败"""
        mock_delete.side_effect = [True, False]

        from duplicate_cleaner.shell_integration import disable_shell_integration
        result = disable_shell_integration()
        assert result is False
