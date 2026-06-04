# Duplicate Cleaner

## 项目背景

重复文件查找与清理工具，基于文件内容哈希精准识别重复文件，支持图形界面和命令行两种模式。

## 技术栈

- Python 3.8+
- tkinter + ttkbootstrap（现代 GUI）
- hashlib / threading / concurrent.futures
- send2trash（安全删除，可选）

## 环境要求

- Python 3.8+
- 无需虚拟环境

## 运行命令

```bash
# 图形界面
python -m duplicate_cleaner

# 命令行模式
python -m duplicate_cleaner --cli /path/to/directory

# 运行测试
python -m pytest tests/ -v
```

## 项目结构

```
duplicate-cleaner/
├── duplicate_cleaner/          # 主模块
│   ├── __init__.py             # 版本信息 (__version__)
│   ├── __main__.py             # 包入口 (python -m)
│   ├── cli.py                  # 命令行界面
│   ├── config.py               # 配置管理 (AppConfig)
│   ├── gui.py                  # 图形界面 (DuplicateCleanerGUI)
│   ├── scanner.py              # 扫描引擎 (FileScanner)
│   └── utils.py                # 公共工具函数
├── tests/                      # 单元测试 (61 个测试)
│   ├── test_cli.py             # CLI 测试
│   ├── test_config.py          # 配置测试
│   ├── test_scanner.py         # 扫描引擎测试
│   └── test_utils.py           # 工具函数测试
├── CLAUDE.md                   # 项目说明（本文件）
├── README.md                   # 用户文档
├── requirements.txt            # 依赖声明
├── pytest.ini                  # 测试配置
└── 启动.bat                    # Windows 启动脚本
```

## 核心模块

### scanner.py - 扫描引擎
- `FileScanner` 类：文件收集、哈希计算、重复检测
- 两阶段哈希：快速哈希（64KB 头部）+ 完整 MD5
- 多线程并行，线程数自适应 CPU 核心数
- 线程安全：使用 `threading.Lock` 保护共享状态

### config.py - 配置管理
- `AppConfig` dataclass：加载/保存/验证
- 配置文件位置：%APPDATA%/DuplicateCleaner（Windows）
- 支持最近目录列表、文件类型过滤等

### gui.py - 图形界面
- `DuplicateCleanerGUI` 类：仅 UI 逻辑
- 业务逻辑委托给 scanner 和 config
- 搜索防抖（300ms）
- send2trash 可用性检查

### cli.py - 命令行界面
- 复用 scanner 和 utils
- 支持 --dry-run、--auto、--trash 等参数

## 已完成功能

- [x] 双击打开文件（系统默认程序）
- [x] 右键菜单：打开文件、打开所在目录、复制路径/文件名、文件属性
- [x] 删除前安全检查：确保每组至少保留一个文件
- [x] 菜单栏：文件/视图/设置/帮助
- [x] 快捷键支持：Ctrl+O/S/E/Q、F1、F5
- [x] 列头排序：点击组号、大小、修改时间、路径列头可排序
- [x] 安全删除：支持移到回收站或永久删除
- [x] 配置保存：自动保存窗口大小、字体、目录等设置
- [x] 文件类型过滤：只扫描图片/视频/音频/文档/压缩包
- [x] 单实例模式：可配置是否只允许一个窗口实例
- [x] 搜索过滤：输入关键词实时过滤结果
- [x] 最近目录：下拉菜单显示最近扫描的目录
- [x] 自动选中：扫描完成自动选中推荐删除的文件
- [x] 修改时间列：显示文件最后修改时间
- [x] 拖放支持：拖放目录到窗口自动填入
- [x] 文件属性：右键查看文件详细属性
- [x] 深色模式：使用 ttkbootstrap darkly 主题
- [x] 扫描结果保存/加载：保存为 JSON 格式，可随时加载
- [x] 移动到文件夹：将选中的重复文件移动到指定文件夹
- [x] 并发优化：自动检测硬盘类型（SSD/HDD），自适应调整线程数
- [x] 文件图标：列表中显示文件类型图标（按颜色区分类型）
- [x] 系统托盘：最小化到系统托盘，双击恢复
- [x] 窗口居中显示
- [x] 单元测试：61 个测试覆盖核心功能

## 待办事项

- [ ] 支持选择哈希算法（MD5/SHA256/SHA1）
- [ ] 支持文件预览（图片、视频缩略图）
- [ ] 添加深色模式
- [ ] 支持拖拽目录到窗口
- [ ] 添加扫描历史记录
