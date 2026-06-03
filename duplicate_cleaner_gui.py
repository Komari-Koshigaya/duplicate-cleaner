#!/usr/bin/env python3
"""
重复文件清理工具 - 图形界面版（高性能 + 现代UI）
"""

import os
import sys
import json
import hashlib
import threading
import subprocess
import tkinter as tk
from tkinter import messagebox, constants
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置文件路径
CONFIG_FILE = Path.home() / ".duplicate_cleaner_config.json"
LOCK_FILE = Path.home() / ".duplicate_cleaner.lock"

# tkinter 常量
BOTH = constants.BOTH
LEFT = constants.LEFT
RIGHT = constants.RIGHT
TOP = constants.TOP
BOTTOM = constants.BOTTOM
CENTER = constants.CENTER
X = constants.X
Y = constants.Y
NORMAL = constants.NORMAL
DISABLED = constants.DISABLED
VERTICAL = constants.VERTICAL
HORIZONTAL = constants.HORIZONTAL
W = constants.W
E = constants.E
END = constants.END

# 延迟导入 ttkbootstrap，加快启动
HAS_BOOTSTRAP = False
ttk = None

def _init_ttk():
    global ttk, HAS_BOOTSTRAP
    if ttk is not None:
        return
    try:
        import ttkbootstrap as _ttk
        ttk = _ttk
        HAS_BOOTSTRAP = True
    except ImportError:
        from tkinter import ttk as _ttk
        ttk = _ttk
        HAS_BOOTSTRAP = False

# 快速哈希只读取头部
QUICK_HASH_SIZE = 65536  # 64KB


class DuplicateCleanerGUI:
    def __init__(self, root):
        _init_ttk()  # 初始化 ttk

        self.root = root
        self.root.title("Duplicate Cleaner - 重复文件清理工具")
        self.root.geometry("1300x800")
        self.root.minsize(1000, 600)

        # 数据存储
        self.duplicates: List[Tuple[str, List[str], int]] = []
        self.selected_files: set = set()
        self.scanning = False
        self.cancel_flag = False

        # 字体配置
        self.font_size_var = tk.StringVar(value="中")
        self.font_sizes = {
            "小": {"base": 9, "title": 16, "tree": 9, "row": 24},
            "中": {"base": 10, "title": 18, "tree": 10, "row": 28},
            "大": {"base": 12, "title": 22, "tree": 12, "row": 34},
        }

        # 窗口大小配置
        self.window_size_var = tk.StringVar(value="中")
        self.window_sizes = {
            "小": (1000, 600),
            "中": (1300, 800),
            "大": (1600, 1000),
        }

        # 文件类型过滤
        self.file_filter_var = tk.StringVar(value="所有文件")
        self.file_filters = {
            "所有文件": [],
            "图片": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
            "视频": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
            "音频": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"],
            "文档": [".doc", ".docx", ".pdf", ".txt", ".xls", ".xlsx", ".ppt", ".pptx"],
            "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
        }

        # 排序状态
        self.sort_column = None
        self.sort_reverse = False

        # 单实例模式
        self.single_instance_var = tk.BooleanVar(value=True)

        # 样式配置
        self._setup_style()

        # 构建界面
        self._build_ui()

        # 创建菜单栏
        self._create_menu()

        # 加载配置（在界面创建之后）
        self._load_config()

        # 绑定关闭事件保存配置
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self):
        """配置样式"""
        style = ttk.Style()

        if HAS_BOOTSTRAP:
            # ttkbootstrap 主题
            style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        else:
            style.theme_use("clam")
            style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self):
        """构建界面"""
        # 主容器 - 先放底部，再放内容
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # ===== 底部操作区（先放，固定在底部） =====
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=X, side=BOTTOM, pady=(8, 0))

        # 状态栏（最底部）
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=X, side=BOTTOM, pady=(4, 0))

        self.status_detail_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.status_detail_var, font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=LEFT)

        # 快捷键提示
        ttk.Label(status_frame, text="Ctrl+O 打开 | Ctrl+S 扫描 | F1 帮助", font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=RIGHT)

        # 统计信息和操作按钮
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=X, side=BOTTOM, pady=(4, 0))

        # 统计信息（左侧）
        self.info_var = tk.StringVar(value="")
        ttk.Label(info_frame, textvariable=self.info_var, font=("Microsoft YaHei UI", 9)).pack(side=LEFT)

        # 操作按钮（右侧）
        action_btn_frame = ttk.Frame(info_frame)
        action_btn_frame.pack(side=RIGHT)

        self.delete_btn = ttk.Button(
            action_btn_frame,
            text="🗑️ 删除选中",
            command=self._delete_selected,
            state=DISABLED,
            bootstyle="danger" if HAS_BOOTSTRAP else None
        )
        self.delete_btn.pack(side=RIGHT, padx=(8, 0))

        ttk.Button(action_btn_frame, text="取消选择", command=self._clear_selection).pack(side=RIGHT, padx=2)
        ttk.Button(action_btn_frame, text="反选", command=self._invert_selection).pack(side=RIGHT, padx=2)
        ttk.Button(action_btn_frame, text="全选重复", command=self._select_second).pack(side=RIGHT, padx=2)

        ttk.Separator(action_btn_frame, orient=VERTICAL).pack(side=RIGHT, fill=Y, padx=6)

        ttk.Button(action_btn_frame, text="📊 导出", command=self._export_results).pack(side=RIGHT, padx=2)
        ttk.Button(action_btn_frame, text="🔍 搜索", command=self._focus_search).pack(side=RIGHT, padx=2)

        # ===== 顶部标题区 =====
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 10))

        title_label = ttk.Label(
            header_frame,
            text="🔍 Duplicate Cleaner",
            font=("Microsoft YaHei UI", 18, "bold")
        )
        title_label.pack(side=LEFT)

        subtitle_label = ttk.Label(
            header_frame,
            text="智能重复文件查找与清理",
            font=("Microsoft YaHei UI", 10),
            foreground="gray"
        )
        subtitle_label.pack(side=LEFT, padx=(10, 0), pady=(5, 0))

        # ===== 扫描配置区 =====
        config_outer = ttk.LabelFrame(main_frame, text=" 扫描配置 ")
        config_outer.pack(fill=X, pady=(0, 10), padx=5)
        config_frame = ttk.Frame(config_outer, padding=12)
        config_frame.pack(fill=X)

        # 第一行：目录选择
        dir_frame = ttk.Frame(config_frame)
        dir_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(dir_frame, text="目录:", width=6).pack(side=LEFT)

        self.dir_var = tk.StringVar()
        self.dir_combo = ttk.Combobox(dir_frame, textvariable=self.dir_var)
        self.dir_combo.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))

        ttk.Button(
            dir_frame,
            text="📂 浏览",
            command=self._browse_dir,
            bootstyle="outline" if HAS_BOOTSTRAP else None
        ).pack(side=LEFT)

        # 第二行：选项和按钮
        action_frame = ttk.Frame(config_frame)
        action_frame.pack(fill=X)

        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(action_frame, text="递归子目录", variable=self.recursive_var).pack(side=LEFT)

        ttk.Label(action_frame, text="最小:").pack(side=LEFT, padx=(15, 5))
        self.min_size_var = tk.StringVar(value="0")
        ttk.Entry(action_frame, textvariable=self.min_size_var, width=8).pack(side=LEFT)
        ttk.Label(action_frame, text="字节").pack(side=LEFT, padx=(2, 0))

        # 按钮区
        btn_frame = ttk.Frame(action_frame)
        btn_frame.pack(side=RIGHT)

        self.scan_btn = ttk.Button(
            btn_frame,
            text="🔍 开始扫描",
            command=self._start_scan,
            bootstyle="success" if HAS_BOOTSTRAP else None
        )
        self.scan_btn.pack(side=LEFT, padx=(0, 5))

        self.cancel_btn = ttk.Button(
            btn_frame,
            text="⏹ 停止",
            command=self._cancel_scan,
            state=DISABLED,
            bootstyle="danger" if HAS_BOOTSTRAP else None
        )
        self.cancel_btn.pack(side=LEFT)

        # ===== 进度区 =====
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=X, pady=(0, 10))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            bootstyle="success-striped" if HAS_BOOTSTRAP else None
        )
        self.progress_bar.pack(fill=X, side=LEFT, expand=True)

        self.status_var = tk.StringVar(value="就绪 - 请选择目录开始扫描")
        ttk.Label(progress_frame, textvariable=self.status_var, width=50, anchor=W).pack(side=LEFT, padx=(10, 0))

        # ===== 结果列表区 =====
        list_outer = ttk.LabelFrame(main_frame, text=" 扫描结果 ")
        list_outer.pack(fill=BOTH, expand=True, pady=(0, 10), padx=5)

        # 搜索过滤框
        search_frame = ttk.Frame(list_outer)
        search_frame.pack(fill=X, padx=8, pady=(8, 0))
        ttk.Label(search_frame, text="🔍 搜索:").pack(side=LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=LEFT, fill=X, expand=True, padx=(5, 10))
        ttk.Label(search_frame, text="输入关键词过滤结果", foreground="gray").pack(side=LEFT)

        list_frame = ttk.Frame(list_outer, padding=8)
        list_frame.pack(fill=BOTH, expand=True)

        # Treeview
        columns = ("select", "group", "size", "path", "hash")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")

        # 列配置
        self.tree.heading("select", text="✓", anchor=CENTER)
        self.tree.heading("group", text="组号 ↕", anchor=CENTER, command=lambda: self._sort_tree("group"))
        self.tree.heading("size", text="大小 ↕", anchor=E, command=lambda: self._sort_tree("size"))
        self.tree.heading("path", text="文件路径 ↕", anchor=W, command=lambda: self._sort_tree("path"))
        self.tree.heading("hash", text="哈希值", anchor=W)

        self.tree.column("select", width=40, minwidth=40, anchor=CENTER)
        self.tree.column("group", width=60, minwidth=50, anchor=CENTER)
        self.tree.column("size", width=100, minwidth=80, anchor=E)
        self.tree.column("path", width=500, minwidth=200)
        self.tree.column("hash", width=350, minwidth=280)

        # 滚动条（只保留垂直滚动条）
        scrollbar_y = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar_y.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")

        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # 绑定事件
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)

        # 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0, font=("Microsoft YaHei UI", 9))
        self.context_menu.add_command(label="📄 打开文件", command=self._open_file)
        self.context_menu.add_command(label="📁 打开所在目录", command=self._open_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📋 复制路径", command=self._copy_path)

        # 快捷键绑定
        self.root.bind("<Control-o>", lambda e: self._browse_dir())
        self.root.bind("<Control-s>", lambda e: self._start_scan())
        self.root.bind("<Control-e>", lambda e: self._export_results())
        self.root.bind("<Control-q>", lambda e: self.root.quit())
        self.root.bind("<F1>", lambda e: self._show_help())
        self.root.bind("<F5>", lambda e: self._start_scan())

        # 标签样式
        self.tree.tag_configure("original", background="#e8f5e9", foreground="#2e7d32")
        self.tree.tag_configure("duplicate", background="#fff8e1", foreground="#f57f17")
        self.tree.tag_configure("selected", background="#e3f2fd", foreground="#1565c0")

    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # ===== 文件菜单 =====
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="📂 选择目录", command=self._browse_dir, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="📊 导出扫描结果", command=self._export_results, accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="❌ 退出", command=self._on_close, accelerator="Ctrl+Q")

        # ===== 视图菜单 =====
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=view_menu)

        # 窗口大小子菜单
        window_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="窗口大小", menu=window_menu)

        for size in ["小", "中", "大"]:
            w, h = self.window_sizes[size]
            window_menu.add_radiobutton(
                label=f"{size}  ({w}×{h})",
                variable=self.window_size_var,
                value=size,
                command=lambda s=size: self._change_window_size(s)
            )

        # 字体大小子菜单
        font_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="字体大小", menu=font_menu)

        for size in ["小", "中", "大"]:
            font_menu.add_radiobutton(
                label=size,
                variable=self.font_size_var,
                value=size,
                command=lambda s=size: self._change_font_size(s)
            )

        view_menu.add_separator()
        view_menu.add_command(label="恢复默认", command=self._reset_view)

        # ===== 设置菜单 =====
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)

        settings_menu.add_checkbutton(
            label="🔒 单实例模式（只允许一个窗口）",
            variable=self.single_instance_var,
            command=self._on_single_instance_change,
        )

        settings_menu.add_separator()

        # 文件类型过滤子菜单
        filter_menu = tk.Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="📁 文件类型过滤", menu=filter_menu)

        for filter_name in self.file_filters.keys():
            filter_menu.add_radiobutton(
                label=filter_name,
                variable=self.file_filter_var,
                value=filter_name,
            )

        settings_menu.add_separator()
        settings_menu.add_checkbutton(
            label="🔊 扫描完成提示音",
            command=self._toggle_sound,
        )

        # ===== 帮助菜单 =====
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="📖 使用说明", command=self._show_help, accelerator="F1")
        help_menu.add_command(label="⌨️ 快捷键", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="ℹ️ 关于", command=self._show_about)

        # 状态变量
        self.sound_enabled = False

    def _change_window_size(self, size: str):
        """切换窗口大小"""
        w, h = self.window_sizes[size]
        # 居中显示
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _change_font_size(self, size: str):
        """切换字体大小"""
        config = self.font_sizes[size]
        style = ttk.Style()

        # 更新 Treeview 样式
        style.configure("Treeview",
                        rowheight=config["row"],
                        font=("Microsoft YaHei UI", config["tree"]))
        style.configure("Treeview.Heading",
                        font=("Microsoft YaHei UI", config["tree"], "bold"))

        # 更新标题字体
        for widget in self.root.winfo_children():
            self._update_widget_fonts(widget, config)

    def _update_widget_fonts(self, widget, config):
        """递归更新组件字体"""
        try:
            if isinstance(widget, ttk.Label):
                current_font = widget.cget("font")
                if current_font and "18" in str(current_font):
                    widget.configure(font=("Microsoft YaHei UI", config["title"], "bold"))
                elif current_font:
                    widget.configure(font=("Microsoft YaHei UI", config["base"]))
        except:
            pass

        for child in widget.winfo_children():
            self._update_widget_fonts(child, config)

    def _reset_view(self):
        """恢复默认视图设置"""
        self.font_size_var.set("中")
        self.window_size_var.set("中")
        self._change_font_size("中")
        self._change_window_size("中")

    def _on_single_instance_change(self):
        """单实例模式切换时立即保存"""
        self._save_config()

        if self.single_instance_var.get():
            # 开启单实例模式，写入锁文件
            try:
                with open(LOCK_FILE, 'w') as f:
                    f.write(str(os.getpid()))
            except:
                pass
            messagebox.showinfo("设置已保存", "单实例模式已开启\n再次启动将跳转到此窗口")
        else:
            # 关闭单实例模式，删除锁文件
            try:
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink()
            except:
                pass
            messagebox.showinfo("设置已保存", "单实例模式已关闭\n现在可以直接启动新窗口")

    def _load_config(self):
        """加载配置"""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.font_size_var.set(config.get("font_size", "中"))
                    self.window_size_var.set(config.get("window_size", "中"))
                    self.sound_enabled = config.get("sound_enabled", False)
                    self.recursive_var.set(config.get("recursive", True))
                    self.min_size_var.set(config.get("min_size", "0"))
                    self.file_filter_var.set(config.get("file_filter", "所有文件"))
                    self.single_instance_var.set(config.get("single_instance", True))

                    # 加载最近目录列表
                    self.recent_dirs = config.get("recent_dirs", [])
                    self.dir_combo['values'] = self.recent_dirs

                    last_dir = config.get("last_dir", "")
                    if last_dir:
                        self.dir_var.set(last_dir)
        except:
            self.recent_dirs = []

    def _save_config(self):
        """保存配置"""
        try:
            current_dir = self.dir_var.get()
            # 更新最近目录列表
            if current_dir and current_dir not in self.recent_dirs:
                self.recent_dirs.insert(0, current_dir)
                self.recent_dirs = self.recent_dirs[:10]  # 只保留最近10个
                self.dir_combo['values'] = self.recent_dirs

            config = {
                "font_size": self.font_size_var.get(),
                "window_size": self.window_size_var.get(),
                "sound_enabled": self.sound_enabled,
                "last_dir": current_dir,
                "recent_dirs": self.recent_dirs,
                "recursive": self.recursive_var.get(),
                "min_size": self.min_size_var.get(),
                "file_filter": self.file_filter_var.get(),
                "single_instance": self.single_instance_var.get(),
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _on_close(self):
        """关闭窗口时保存配置"""
        self._save_config()

        # 只在关闭单实例模式时删除锁文件
        # 如果开启单实例模式，保留锁文件直到进程结束
        if not self.single_instance_var.get():
            try:
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink()
            except:
                pass

        self.root.destroy()

    def _on_search_change(self, *args):
        """搜索框内容变化时过滤显示"""
        keyword = self.search_var.get().lower().strip()
        if not keyword:
            # 显示所有
            for item in self.tree.get_children():
                self.tree.reattach(item, "", END)
            return

        # 过滤显示
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            filepath = str(values[3]).lower()
            file_hash = str(values[4]).lower()
            if keyword in filepath or keyword in file_hash:
                self.tree.reattach(item, "", END)
            else:
                self.tree.detach(item)

    def _focus_search(self):
        """聚焦搜索框"""
        # 直接聚焦到搜索框
        if hasattr(self, 'search_var'):
            # 找到搜索框的父组件
            for widget in self.root.winfo_children():
                self._find_search_entry(widget)

    def _find_search_entry(self, widget):
        """递归查找搜索框"""
        try:
            if isinstance(widget, ttk.Entry):
                # 检查是否绑定到 search_var
                if str(widget.cget("textvariable")) == str(self.search_var):
                    widget.focus_set()
                    return True
        except:
            pass
        for child in widget.winfo_children():
            if self._find_search_entry(child):
                return True
        return False

    def _toggle_sound(self):
        """切换扫描完成提示音"""
        self.sound_enabled = not self.sound_enabled
        status = "开启" if self.sound_enabled else "关闭"
        messagebox.showinfo("提示音", f"扫描完成提示音已{status}")

    def _export_results(self):
        """导出扫描结果"""
        if not self.duplicates:
            messagebox.showinfo("提示", "没有可导出的扫描结果，请先扫描")
            return

        from tkinter import filedialog
        import csv

        filepath = filedialog.asksaveasfilename(
            title="导出扫描结果",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")]
        )

        if not filepath:
            return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["组号", "文件大小", "哈希值", "文件路径", "是否选中删除"])

                for i, (file_hash, files, size) in enumerate(self.duplicates, 1):
                    for j, file_path in enumerate(files):
                        selected = "是" if file_path in self.selected_files else "否"
                        writer.writerow([
                            f"#{i}",
                            self._format_size(size),
                            file_hash,
                            file_path,
                            selected
                        ])

            messagebox.showinfo("成功", f"扫描结果已导出到:\n{filepath}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _show_help(self):
        """显示使用说明"""
        help_text = """📖 使用说明

1. 选择目录
   点击「浏览」按钮选择要扫描的目录

2. 设置选项
   • 递归子目录：是否扫描子文件夹
   • 最小文件大小：忽略小于此大小的文件
   • 文件类型：工具 → 文件类型过滤

3. 开始扫描
   点击「🔍 开始扫描」按钮
   扫描过程中可点击「⏹ 停止」终止

4. 查看结果
   • 绿色行：每组第一个文件（建议保留）
   • 橙色行：重复文件（建议删除）
   • 双击文件可打开预览
   • 右键可打开文件/所在目录/复制路径
   • 点击列头可排序

5. 选择删除
   • 点击「全选重复」快速选择
   • 手动点击勾选框选择
   • 点击「🗑️ 删除选中」确认删除
   • 可选择移到回收站或永久删除

6. 安全机制
   • 删除前会检查每组至少保留一个文件
   • 删除前需要二次确认
   • 显示释放空间大小

7. 窗口设置（工具菜单）
   • 单实例模式：默认开启，多次启动只打开一个窗口
     取消勾选后可同时打开多个窗口
   • 窗口大小：视图 → 窗口大小（小/中/大）
   • 字体大小：视图 → 字体大小（小/中/大）

8. 其他功能
   • 导出结果：工具 → 导出扫描结果（CSV）
   • 提示音：工具 → 扫描完成提示音"""

        help_win = tk.Toplevel(self.root)
        help_win.title("使用说明")
        help_win.geometry("500x600")
        help_win.transient(self.root)

        text = tk.Text(help_win, wrap=tk.WORD, padx=15, pady=15, font=("Microsoft YaHei UI", 10))
        text.pack(fill=tk.BOTH, expand=True)
        text.insert(tk.END, help_text)
        text.configure(state=tk.DISABLED)

        scrollbar = ttk.Scrollbar(help_win, command=text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=scrollbar.set)

    def _show_shortcuts(self):
        """显示快捷键"""
        shortcuts_text = """⌨️ 快捷键

Ctrl+O    选择目录
Ctrl+S    开始扫描
Ctrl+E    导出结果
Ctrl+Q    退出程序
F1        显示帮助
F5        刷新扫描"""

        messagebox.showinfo("快捷键", shortcuts_text)

    def _show_about(self):
        """显示关于信息"""
        about_text = """🔍 Duplicate Cleaner
重复文件清理工具

版本：v1.1.0
作者：Claude AI
日期：2025年

功能特点：
• 基于文件内容哈希精准识别重复
• 多线程并行扫描，速度快
• 支持图形界面，操作简单
• 安全删除机制，防止误删
• 文件类型过滤
• 单实例模式
• 导出扫描结果
• 自定义界面大小和字体

技术栈：
• Python 3.8+
• tkinter + ttkbootstrap
• hashlib / threading / send2trash"""

        messagebox.showinfo("关于", about_text)

    def _browse_dir(self):
        from tkinter import filedialog
        dirpath = filedialog.askdirectory(title="选择要扫描的目录")
        if dirpath:
            self.dir_var.set(dirpath)

    def _cancel_scan(self):
        self.cancel_flag = True
        self.cancel_btn.configure(state=DISABLED)
        self._update_status("正在取消...")

    def _start_scan(self):
        directory = self.dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showerror("错误", "请选择有效的目录")
            return

        if self.scanning:
            return

        self.scanning = True
        self.cancel_flag = False
        self.scan_btn.configure(state=DISABLED)
        self.cancel_btn.configure(state=NORMAL)
        self.delete_btn.configure(state=DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.duplicates.clear()
        self.selected_files.clear()
        self.info_var.set("")
        self.search_var.set("")  # 清空搜索框

        thread = threading.Thread(target=self._scan_worker, args=(directory,), daemon=True)
        thread.start()

    def _scan_worker(self, directory: str):
        """优化的扫描工作线程"""
        try:
            recursive = self.recursive_var.get()
            try:
                min_size = int(self.min_size_var.get())
            except ValueError:
                min_size = 0

            # 获取文件类型过滤
            filter_name = self.file_filter_var.get()
            filter_exts = self.file_filters.get(filter_name, [])

            # 第一阶段：收集文件
            self._update_status("🔍 正在扫描文件...")
            self._update_progress(0)

            size_groups: Dict[int, List[str]] = defaultdict(list)
            base_path = Path(directory)
            pattern = '**/*' if recursive else '*'

            file_count = 0
            for item in base_path.glob(pattern):
                if self.cancel_flag:
                    self._update_status("已取消")
                    return

                if item.is_file():
                    # 文件类型过滤
                    if filter_exts and item.suffix.lower() not in filter_exts:
                        continue

                    try:
                        size = item.stat().st_size
                        if size >= min_size:
                            size_groups[size].append(str(item))
                            file_count += 1
                    except (PermissionError, OSError):
                        continue

            self._update_status(f"📁 扫描到 {file_count} 个文件，正在筛选...")

            # 第二阶段：按大小筛选
            candidates: List[str] = []
            for size, files in size_groups.items():
                if len(files) > 1:
                    candidates.extend(files)

            if not candidates:
                self.root.after(0, lambda: self._display_results())
                self._update_status("✅ 扫描完成，未发现重复文件")
                return

            self._update_status(f"🔄 发现 {len(candidates)} 个可能重复的文件，正在计算哈希...")

            # 第三阶段：多线程快速哈希
            quick_hashes: Dict[str, List[str]] = defaultdict(list)
            processed = 0
            total = len(candidates)

            def calc_quick_hash(filepath: str) -> Tuple[str, Optional[str]]:
                try:
                    with open(filepath, 'rb') as f:
                        data = f.read(QUICK_HASH_SIZE)
                    return filepath, hashlib.md5(data).hexdigest()
                except (PermissionError, OSError):
                    return filepath, None

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(calc_quick_hash, f): f for f in candidates}

                for future in as_completed(futures):
                    if self.cancel_flag:
                        for f in futures:
                            f.cancel()
                        self._update_status("已取消")
                        return

                    filepath, quick_hash = future.result()
                    processed += 1

                    if quick_hash:
                        quick_hashes[quick_hash].append(filepath)

                    if processed % 50 == 0 or processed == total:
                        self._update_progress(processed / total * 60)
                        self._update_status(f"⚡ 快速哈希: {processed}/{total}")

            # 第四阶段：完整哈希验证
            full_hash_candidates: List[str] = []
            for quick_hash, files in quick_hashes.items():
                if len(files) > 1:
                    full_hash_candidates.extend(files)

            if not full_hash_candidates:
                self.root.after(0, lambda: self._display_results())
                self._update_status("✅ 扫描完成，未发现重复文件")
                return

            self._update_status(f"🔎 发现 {len(full_hash_candidates)} 个快速哈希相同的文件，正在精确验证...")

            full_hashes: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
            processed = 0
            total = len(full_hash_candidates)

            def calc_full_hash(filepath: str) -> Tuple[str, Optional[str]]:
                try:
                    md5 = hashlib.md5()
                    with open(filepath, 'rb') as f:
                        while chunk := f.read(131072):
                            md5.update(chunk)
                    return filepath, md5.hexdigest()
                except (PermissionError, OSError):
                    return filepath, None

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(calc_full_hash, f): f for f in full_hash_candidates}

                for future in as_completed(futures):
                    if self.cancel_flag:
                        for f in futures:
                            f.cancel()
                        self._update_status("已取消")
                        return

                    filepath, full_hash = future.result()
                    processed += 1

                    if full_hash:
                        size = os.path.getsize(filepath)
                        full_hashes[full_hash].append((filepath, size))

                    if processed % 20 == 0 or processed == total:
                        self._update_progress(60 + processed / total * 40)
                        self._update_status(f"🔎 精确验证: {processed}/{total}")

            # 第五阶段：整理结果
            self.duplicates.clear()
            for file_hash, files_info in full_hashes.items():
                if len(files_info) > 1:
                    files = [f[0] for f in files_info]
                    size = files_info[0][1]
                    self.duplicates.append((file_hash, files, size))

            self.duplicates.sort(key=lambda x: x[2], reverse=True)

            self.root.after(0, self._display_results)

        except Exception as e:
            if not self.cancel_flag:
                self.root.after(0, lambda: messagebox.showerror("错误", f"扫描出错: {e}"))
        finally:
            self.scanning = False
            self.root.after(0, self._reset_buttons)

    def _reset_buttons(self):
        self.scan_btn.configure(state=NORMAL)
        self.cancel_btn.configure(state=DISABLED)
        if not self.duplicates:
            self.delete_btn.configure(state=DISABLED)

    def _display_results(self):
        self.tree.delete(*self.tree.get_children())
        self.selected_files.clear()

        if not self.duplicates:
            self.info_var.set("✨ 未发现重复文件")
            self._update_status("✅ 扫描完成，未发现重复文件")
            self._update_progress(100)
            if self.sound_enabled:
                self.root.bell()
            return

        total_groups = len(self.duplicates)
        total_files = sum(len(files) for _, files, _ in self.duplicates)
        total_wasted = sum(size * (len(files) - 1) for _, files, size in self.duplicates)

        self._update_status(f"✅ 扫描完成: {total_groups} 组重复")
        self._update_progress(100)

        # 扫描完成提示音
        if self.sound_enabled:
            self.root.bell()

        # 批量插入
        self.tree.configure(selectmode="none")

        for i, (file_hash, files, size) in enumerate(self.duplicates, 1):
            for j, filepath in enumerate(files):
                select_mark = "⬜" if j == 0 else "☐"
                tag = "original" if j == 0 else "duplicate"
                self.tree.insert("", END, values=(
                    select_mark,
                    f"#{i}",
                    self._format_size(size),
                    filepath,
                    file_hash
                ), tags=(tag,))

        self.tree.configure(selectmode="extended")

        # 自动选中推荐删除的文件（每组第一个保留，其余选中）
        self._select_second()

        self.info_var.set(
            f"📊 共 {total_groups} 组重复，{total_files} 个文件，可释放 {self._format_size(total_wasted)}"
        )
        self.delete_btn.configure(state=NORMAL)

    def _sort_tree(self, col: str):
        """点击列头排序"""
        # 切换排序方向
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        # 获取所有项目
        items = [(self.tree.set(item, col), item) for item in self.tree.get_children()]

        # 排序
        if col == "size":
            # 按大小排序需要转换
            def parse_size(s):
                parts = s.split()
                if len(parts) == 2:
                    num = float(parts[0])
                    unit = parts[1]
                    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
                    return num * multipliers.get(unit, 1)
                return 0
            items.sort(key=lambda x: parse_size(x[0]), reverse=self.sort_reverse)
        elif col == "group":
            # 按组号排序
            items.sort(key=lambda x: int(x[0].replace("#", "")), reverse=self.sort_reverse)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=self.sort_reverse)

        # 重新排列项目
        for index, (val, item) in enumerate(items):
            self.tree.move(item, "", index)

        # 更新列头显示排序方向
        for c in ["group", "size", "path"]:
            current_text = self.tree.heading(c, "text")
            if c == col:
                arrow = " ↓" if self.sort_reverse else " ↑"
                self.tree.heading(c, text=current_text.replace(" ↑", "").replace(" ↓", "") + arrow)
            else:
                self.tree.heading(c, text=current_text.replace(" ↑", "").replace(" ↓", ""))

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)

        if not row or column != "#1":
            return

        values = self.tree.item(row, "values")
        filepath = values[3]

        if filepath in self.selected_files:
            self.selected_files.discard(filepath)
            self.tree.set(row, "select", "☐")
        else:
            self.selected_files.add(filepath)
            self.tree.set(row, "select", "☑")

    def _get_clicked_filepath(self, event) -> Optional[str]:
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        values = self.tree.item(row, "values")
        return values[3] if values else None

    def _on_double_click(self, event):
        filepath = self._get_clicked_filepath(event)
        if filepath and os.path.exists(filepath):
            self._open_file_path(filepath)

    def _show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        filepath = self._get_clicked_filepath(event)
        if filepath:
            self.context_menu.post(event.x_root, event.y_root)

    def _open_file(self):
        filepath = self._get_selected_filepath()
        if filepath:
            self._open_file_path(filepath)

    def _open_folder(self):
        filepath = self._get_selected_filepath()
        if filepath:
            self._open_folder_path(filepath)

    def _copy_path(self):
        filepath = self._get_selected_filepath()
        if filepath:
            self.root.clipboard_clear()
            self.root.clipboard_append(filepath)
            self._update_status(f"📋 已复制路径")

    def _get_selected_filepath(self) -> Optional[str]:
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        return values[3] if values else None

    def _open_file_path(self, filepath: str):
        try:
            if os.name == 'nt':
                os.startfile(filepath)
            elif os.name == 'posix':
                subprocess.call(['open', filepath] if sys.platform == 'darwin' else ['xdg-open', filepath])
            self._update_status(f"📄 已打开文件")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件:\n{e}")

    def _open_folder_path(self, filepath: str):
        try:
            if os.name == 'nt':
                subprocess.run(['explorer', '/select,', filepath])
            elif os.name == 'posix':
                if sys.platform == 'darwin':
                    subprocess.run(['open', '-R', filepath])
                else:
                    subprocess.run(['xdg-open', os.path.dirname(filepath)])
            self._update_status(f"📁 已打开目录")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开目录:\n{e}")

    def _select_second(self):
        self.selected_files.clear()
        for _, files, _ in self.duplicates:
            for j, filepath in enumerate(files):
                if j > 0:
                    self.selected_files.add(filepath)
        self._refresh_checkmarks()

    def _invert_selection(self):
        all_files = set()
        for _, files, _ in self.duplicates:
            all_files.update(files[1:])
        self.selected_files = all_files - self.selected_files
        self._refresh_checkmarks()

    def _clear_selection(self):
        self.selected_files.clear()
        self._refresh_checkmarks()

    def _refresh_checkmarks(self):
        original_files = set()
        for _, files, _ in self.duplicates:
            original_files.add(files[0])

        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            filepath = values[3]

            if filepath in self.selected_files:
                self.tree.set(item, "select", "☑")
            else:
                self.tree.set(item, "select", "⬜" if filepath in original_files else "☐")

    def _delete_selected(self):
        if not self.selected_files:
            messagebox.showinfo("提示", "请先选择要删除的文件")
            return

        # 检查每组是否至少保留一个文件
        empty_groups = []
        for i, (file_hash, files, size) in enumerate(self.duplicates, 1):
            remaining = [f for f in files if f not in self.selected_files]
            if not remaining:
                empty_groups.append(i)

        if empty_groups:
            groups_str = ", ".join([f"#{g}" for g in empty_groups[:5]])
            if len(empty_groups) > 5:
                groups_str += f" 等共 {len(empty_groups)} 组"

            messagebox.showwarning(
                "⚠️ 警告",
                f"以下重复组的所有文件都被选中删除：\n\n"
                f"第 {groups_str} 组\n\n"
                f"请至少为每组保留一个文件。"
            )
            return

        # 统计信息
        files_list = sorted(self.selected_files)
        count = len(files_list)
        total_size = sum(os.path.getsize(f) for f in files_list if os.path.exists(f))

        # 选择删除方式
        delete_to_trash = messagebox.askyesno(
            "删除方式",
            f"确定要删除以下 {count} 个文件吗？\n\n"
            f"💾 释放空间: {self._format_size(total_size)}\n\n"
            f"选择「是」移到回收站（可恢复）\n"
            f"选择「否」永久删除（不可恢复）"
        )

        if delete_to_trash is None:
            return

        success = 0
        failed = 0
        errors = []

        try:
            import send2trash
            use_trash = delete_to_trash
        except ImportError:
            use_trash = False

        for filepath in files_list:
            try:
                if use_trash:
                    send2trash.send2trash(filepath)
                else:
                    os.remove(filepath)
                success += 1
            except Exception as e:
                failed += 1
                errors.append(f"{filepath}: {e}")

        delete_type = "移到回收站" if use_trash else "永久删除"
        result_msg = f"✅ {delete_type}完成\n\n成功: {success} 个\n失败: {failed} 个"
        if errors:
            result_msg += "\n\n❌ 失败详情:\n" + "\n".join(errors[:5])

        messagebox.showinfo("完成", result_msg)

        if success > 0:
            self._start_scan()

    def _update_status(self, text: str):
        self.root.after(0, lambda: self.status_var.set(text))

    def _update_progress(self, value: float):
        self.root.after(0, lambda: self.progress_var.set(value))

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"


def check_single_instance():
    """检查是否已有实例在运行"""
    try:
        if LOCK_FILE.exists():
            # 读取锁文件中的进程ID
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())

            # 检查进程是否还在运行
            if sys.platform == 'win32':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True  # 进程还在运行
            else:
                import signal
                try:
                    os.kill(pid, 0)
                    return True  # 进程还在运行
                except OSError:
                    pass

            # 进程不在运行，删除旧的锁文件
            LOCK_FILE.unlink()
    except:
        pass

    # 写入当前进程ID
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except:
        pass

    return False


def activate_existing_window():
    """激活已存在的窗口"""
    try:
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes

            # 查找窗口
            EnumWindows = ctypes.windll.user32.EnumWindows
            GetWindowTextW = ctypes.windll.user32.GetWindowTextW
            GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible
            SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
            ShowWindow = ctypes.windll.user32.ShowWindow

            SW_RESTORE = 9

            class LPARAM(ctypes.Structure):
                pass

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.POINTER(LPARAM))

            target_title = "Duplicate Cleaner"

            def enum_callback(hwnd, lparam):
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        GetWindowTextW(hwnd, buf, length + 1)
                        if target_title in buf.value:
                            ShowWindow(hwnd, SW_RESTORE)
                            SetForegroundWindow(hwnd)
                            return False
                return True

            EnumWindows(WNDENUMPROC(enum_callback), None)
    except:
        pass


def main():
    _init_ttk()  # 初始化 ttk

    # 检查单实例模式
    # 先加载配置看看是否启用了单实例模式
    single_instance = True
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                single_instance = config.get("single_instance", True)
    except:
        pass

    if single_instance and check_single_instance():
        # 已有实例在运行，激活已有窗口
        activate_existing_window()
        return

    if HAS_BOOTSTRAP:
        root = ttk.Window(
            title="Duplicate Cleaner - 重复文件清理工具",
            themename="litera",
            size=(1300, 800),
            minsize=(1200, 700)
        )
    else:
        root = tk.Tk()

    app = DuplicateCleanerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
