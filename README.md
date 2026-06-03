# 🔍 Duplicate Cleaner

重复文件查找与清理工具，基于文件内容哈希精准识别重复文件。

## 功能特点

- ✅ 基于 MD5 哈希准确判断文件内容重复
- ✅ 多线程并行扫描，高性能
- ✅ 图形界面（tkinter + ttkbootstrap）
- ✅ 命令行模式
- ✅ 双击/右键打开文件预览
- ✅ 列头排序、搜索过滤
- ✅ 文件类型过滤（图片/视频/音频/文档/压缩包）
- ✅ 安全删除（回收站/永久删除）
- ✅ 导出扫描结果为 CSV
- ✅ 单实例模式、配置自动保存
- ✅ 窗口大小/字体大小可调
- ✅ 修改时间显示
- ✅ 拖放目录到窗口
- ✅ 文件属性查看

## 项目结构

```
duplicate-cleaner/
├── duplicate_cleaner/          # 主模块
│   ├── __init__.py             # 版本信息
│   ├── __main__.py             # 包入口
│   ├── cli.py                  # 命令行界面
│   ├── config.py               # 配置管理
│   ├── gui.py                  # 图形界面
│   ├── scanner.py              # 扫描引擎
│   └── utils.py                # 公共工具
├── tests/                      # 单元测试
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_scanner.py
│   └── test_utils.py
├── CLAUDE.md                   # 项目说明
├── README.md                   # 用户文档
├── requirements.txt            # 依赖声明
├── pytest.ini                  # 测试配置
└── 启动.bat                    # Windows 启动脚本
```

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 或只安装核心依赖
pip install ttkbootstrap send2trash
```

## 使用方法

### 图形界面

```bash
# 方式一：直接运行
python -m duplicate_cleaner

# 方式二：双击启动.bat
```

### 命令行

```bash
# 扫描并交互式清理
python -m duplicate_cleaner --cli /path/to/directory

# 预览模式
python -m duplicate_cleaner --cli --dry-run /path/to/directory

# 自动模式（保留每组第一个）
python -m duplicate_cleaner --cli --auto /path/to/directory

# 移到回收站
python -m duplicate_cleaner --cli --trash /path/to/directory
```

### 运行测试

```bash
# 运行所有测试
python -m pytest

# 运行特定测试文件
python -m pytest tests/test_scanner.py

# 显示覆盖率
python -m pytest --cov=duplicate_cleaner
```

## 技术栈

- Python 3.8+
- tkinter + ttkbootstrap（GUI）
- hashlib / threading / concurrent.futures
- send2trash（安全删除）

## 许可证

MIT License
