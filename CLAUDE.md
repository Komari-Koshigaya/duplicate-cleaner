# Duplicate Cleaner

## 项目背景

重复文件查找与清理工具，基于文件内容哈希精准识别重复文件，支持图形界面和命令行两种模式。

使用 Claude Code AI 辅助开发。

## 技术栈

- Python 3.8+
- tkinter + ttkbootstrap（现代 GUI）
- xxhash / hashlib（哈希算法，xxhash 比 MD5 快数倍）
- threading / concurrent.futures（多线程）
- os.walk（文件遍历，支持排除目录）
- send2trash（安全删除）
- pystray（系统托盘）
- Pillow（图标生成）
- PyInstaller（打包为 exe）

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

# 打包为 exe
python build.py
```

## 项目结构

```
duplicate-cleaner/
├── duplicate_cleaner/          # 主模块
│   ├── __init__.py             # 版本信息 (v1.3.0)
│   ├── __main__.py             # 包入口 (python -m)
│   ├── cli.py                  # 命令行界面
│   ├── config.py               # 配置管理 (AppConfig)
│   ├── gui.py                  # 图形界面 (DuplicateCleanerGUI)
│   ├── scanner.py              # 扫描引擎 (FileScanner)
│   └── utils.py                # 公共工具函数
├── tests/                      # 单元测试 (61 个测试)
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_scanner.py
│   └── test_utils.py
├── icon.ico                    # 窗口图标
├── icon.png                    # 托盘图标
├── entry.py                    # 打包入口
├── build.py                    # 打包脚本
├── build_debug.py              # 调试版打包脚本
├── CLAUDE.md                   # 项目说明（本文件）
├── README.md                   # 用户文档
├── requirements.txt            # 依赖声明
├── pytest.ini                  # 测试配置
├── 启动.bat                    # Windows 启动脚本
└── 打包.bat                    # Windows 打包脚本
```

## 核心模块

### scanner.py - 扫描引擎
- `FileScanner` 类：文件收集、哈希计算、重复检测
- 两阶段哈希：快速哈希（64KB 头部）+ 完整哈希
- xxhash 优先，MD5 兜底
- 多线程并行，线程数自适应硬盘类型（SSD/HDD）
- 支持排除目录
- 线程安全：使用 `threading.Lock` 保护共享状态

### config.py - 配置管理
- `AppConfig` dataclass：加载/保存/验证
- 配置文件位置：%APPDATA%/DuplicateCleaner（Windows）
- 支持最近目录列表、文件类型过滤、排除目录等
- 配置备份和恢复

### gui.py - 图形界面
- `DuplicateCleanerGUI` 类：仅 UI 逻辑
- 业务逻辑委托给 scanner 和 config
- 搜索防抖（300ms）
- send2trash 可用性检查
- 系统托盘支持
- 多主题选择

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
- [x] 多主题选择：13 种 ttkbootstrap 主题
- [x] 扫描结果保存/加载：保存为 JSON 格式，可随时加载
- [x] 移动到文件夹：将选中的重复文件移动到指定文件夹
- [x] 并发优化：自动检测硬盘类型（SSD/HDD），自适应调整线程数
- [x] 文件图标：列表中显示文件类型图标（按颜色区分类型）
- [x] 系统托盘：最小化到系统托盘，双击恢复
- [x] 关闭行为设置：可选择关闭时退出或最小化到托盘
- [x] 排除目录：可配置排除的目录名（默认排除 node_modules、.git 等）
- [x] 配置备份和恢复
- [x] 自动更新检查：启动时检查 GitHub 最新版本
- [x] 扫描耗时和总文件数显示
- [x] 日志文件记录
- [x] 打包为 exe：支持打包为单个可执行文件
- [x] 窗口居中显示
- [x] 单元测试：61 个测试覆盖核心功能

## 待办事项

- [ ] 支持文件预览（图片、视频缩略图）
- [ ] 相似图片检测（感知哈希）
- [ ] 符号链接替代（节省空间）
- [ ] 扫描报告导出（HTML）
- [ ] 右键菜单集成（Windows）
