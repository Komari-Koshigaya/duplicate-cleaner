"""
打包脚本 - 将项目打包为 exe 文件
"""

import os
import sys
import shutil
from pathlib import Path


def build_exe():
    """打包为 exe 文件"""
    print("=" * 50)
    print("Duplicate Cleaner 打包工具")
    print("=" * 50)

    # 获取项目路径
    project_dir = Path(__file__).parent
    dist_dir = project_dir / "dist"
    build_dir = project_dir / "build"

    # 清理旧的构建文件
    print("\n[1/4] 清理旧文件...")
    for dir_path in [dist_dir, build_dir]:
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                print(f"  删除: {dir_path}")
            except PermissionError:
                print(f"  跳过: {dir_path} (被占用)")

    # PyInstaller 参数
    print("\n[2/4] 配置打包参数...")

    # 图标文件
    icon_path = project_dir / "icon.ico"
    icon_arg = f"--icon={icon_path}" if icon_path.exists() else ""

    # 构建命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # 打包成单个 exe
        "--windowed",                   # 无控制台窗口
        "--name=DuplicateCleaner",      # exe 文件名
        f"--add-data={project_dir / 'icon.ico'};.",  # 添加图标
        f"--add-data={project_dir / 'icon.png'};.",  # 添加图标
        "--hidden-import=ttkbootstrap", # 隐藏导入
        "--hidden-import=pystray",
        "--hidden-import=PIL",
        "--hidden-import=tkinterdnd2",
        "--noconfirm",                  # 不确认覆盖
        "--clean",                      # 清理缓存
    ]

    if icon_path.exists():
        cmd.append(f"--icon={icon_path}")

    # 添加入口文件（使用专门的打包入口）
    cmd.append(str(project_dir / "entry.py"))

    print(f"  命令: {' '.join(cmd)}")

    # 执行打包
    print("\n[3/4] 开始打包（可能需要几分钟）...")
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_dir))

    if result.returncode != 0:
        print(f"\n打包失败!")
        print(f"错误信息:\n{result.stderr}")
        return False

    # 检查结果
    print("\n[4/4] 检查打包结果...")
    exe_path = dist_dir / "DuplicateCleaner.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n打包成功!")
        print(f"  文件: {exe_path}")
        print(f"  大小: {size_mb:.1f} MB")
        print(f"\n可以直接双击运行，无需安装 Python 或任何依赖。")
        return True
    else:
        print(f"\n打包失败，未找到 exe 文件")
        return False


if __name__ == "__main__":
    build_exe()
