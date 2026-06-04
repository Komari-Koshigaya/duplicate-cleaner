"""
打包入口文件 - 使用绝对导入
"""

import sys
import os

# 添加项目路径到 sys.path
if getattr(sys, 'frozen', False):
    # 打包后的路径
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base_dir)

# 导入并运行主程序
from duplicate_cleaner.__main__ import main

if __name__ == "__main__":
    main()
