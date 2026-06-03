"""
图形界面模块

使用 tkinter + ttkbootstrap 构建的现代 GUI。
所有业务逻辑委托给 scanner 和 config 模块。
"""

import os
import sys
import csv
import logging
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog, constants
from typing import Optional
from pathlib import Path
from datetime import datetime

from . import __version__
from .config import AppConfig, FONT_SIZES, WINDOW_SIZES, FILE_FILTERS
from .scanner import FileScanner, ScanResult
from .utils import format_size, is_send2trash_available, get_lock_file

logger = logging.getLogger("duplicate_cleaner")

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
W = constants.W
E = constants.E
END = constants.END

# ttkbootstrap 延迟加载
_ttk = None
_has_bootstrap = False
_tkdnd = None


def _init_ttk():
    """延迟导入 ttkbootstrap"""
    global _ttk, _has_bootstrap
    if _ttk is not None:
        return
    try:
        import ttkbootstrap as tb
        _ttk = tb
        _has_bootstrap = True
    except ImportError:
        from tkinter import ttk
        _ttk = ttk
        _has_bootstrap = False


def _init_tkdnd():
    """延迟导入 tkinterdnd2（拖放支持）"""
    global _tkdnd
    if _tkdnd is not None:
        return _tkdnd
    try:
        import tkinterdnd2
        _tkdnd = tkinterdnd2
        return _tkdnd
    except ImportError:
        return None


class DuplicateCleanerGUI:
    """重复文件清理工具 GUI"""

    def __init__(self, root):
        _init_ttk()

        self.root = root
        self.root.title(f"Duplicate Cleaner v{__version__}")
        self.root.minsize(1000, 600)

        # 窗口居中显示
        w, h = 1300, 800
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # 核心组件
        self.config = AppConfig.load()
        self.scanner = FileScanner()

        # 状态
        self.scan_result = None
        self.selected_files = set()
        self.scanning = False
        self.sort_column = None
        self.sort_reverse = False
        self._search_timer = None

        # 构建界面
        self._setup_style()
        self._build_ui()
        self._create_menu()
        self._apply_config()

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self):
        """配置样式"""
        style = _ttk.Style()
        if _has_bootstrap:
            style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        else:
            style.theme_use("clam")
            style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self):
        """构建界面"""
        main = _ttk.Frame(self.root)
        main.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # 底部（先放）
        self._build_bottom(main)
        # 标题
        self._build_header(main)
        # 配置区
        self._build_config(main)
        # 进度条
        self._build_progress(main)
        # 结果列表
        self._build_result_list(main)

    def _build_bottom(self, parent):
        """底部操作区"""
        # 状态栏
        sf = _ttk.Frame(parent)
        sf.pack(fill=X, side=BOTTOM, pady=(4, 0))
        self.status_detail_var = tk.StringVar(value="就绪")
        _ttk.Label(sf, textvariable=self.status_detail_var, font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=LEFT)
        _ttk.Label(sf, text="Ctrl+O 打开 | Ctrl+S 扫描 | F1 帮助", font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=RIGHT)

        # 操作按钮
        af = _ttk.Frame(parent)
        af.pack(fill=X, side=BOTTOM, pady=(4, 0))
        self.info_var = tk.StringVar(value="")
        _ttk.Label(af, textvariable=self.info_var, font=("Microsoft YaHei UI", 9)).pack(side=LEFT)

        bf = _ttk.Frame(af)
        bf.pack(side=RIGHT)

        self.delete_btn = _ttk.Button(bf, text="🗑️ 删除选中", command=self._delete_selected, state=DISABLED, bootstyle="danger" if _has_bootstrap else None)
        self.delete_btn.pack(side=RIGHT, padx=(8, 0))
        _ttk.Button(bf, text="取消选择", command=self._clear_selection).pack(side=RIGHT, padx=2)
        _ttk.Button(bf, text="反选", command=self._invert_selection).pack(side=RIGHT, padx=2)
        _ttk.Button(bf, text="全选重复", command=self._select_second).pack(side=RIGHT, padx=2)
        _ttk.Separator(bf, orient=VERTICAL).pack(side=RIGHT, fill=Y, padx=6)
        _ttk.Button(bf, text="📊 导出", command=self._export_results).pack(side=RIGHT, padx=2)
        _ttk.Button(bf, text="🔍 搜索", command=self._focus_search).pack(side=RIGHT, padx=2)

    def _build_header(self, parent):
        """标题区"""
        h = _ttk.Frame(parent)
        h.pack(fill=X, pady=(0, 10))
        _ttk.Label(h, text="🔍 Duplicate Cleaner", font=("Microsoft YaHei UI", 18, "bold")).pack(side=LEFT)
        _ttk.Label(h, text="智能重复文件查找与清理", font=("Microsoft YaHei UI", 10), foreground="gray").pack(side=LEFT, padx=(10, 0), pady=(5, 0))

    def _build_config(self, parent):
        """配置区"""
        outer = _ttk.LabelFrame(parent, text=" 扫描配置 ")
        outer.pack(fill=X, pady=(0, 10), padx=5)
        f = _ttk.Frame(outer, padding=12)
        f.pack(fill=X)

        # 目录行
        df = _ttk.Frame(f)
        df.pack(fill=X, pady=(0, 8))
        _ttk.Label(df, text="目录:", width=6).pack(side=LEFT)
        self.dir_var = tk.StringVar()
        self.dir_combo = _ttk.Combobox(df, textvariable=self.dir_var)
        self.dir_combo.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        _ttk.Button(df, text="📂 浏览", command=self._browse_dir, bootstyle="outline" if _has_bootstrap else None).pack(side=LEFT)

        # 选项行
        of = _ttk.Frame(f)
        of.pack(fill=X)
        self.recursive_var = tk.BooleanVar(value=True)
        _ttk.Checkbutton(of, text="递归子目录", variable=self.recursive_var).pack(side=LEFT)
        _ttk.Label(of, text="最小:").pack(side=LEFT, padx=(15, 5))
        self.min_size_var = tk.StringVar(value="0")
        _ttk.Entry(of, textvariable=self.min_size_var, width=8).pack(side=LEFT)
        _ttk.Label(of, text="字节").pack(side=LEFT, padx=(2, 0))

        bf = _ttk.Frame(of)
        bf.pack(side=RIGHT)
        self.scan_btn = _ttk.Button(bf, text="🔍 开始扫描", command=self._start_scan, bootstyle="success" if _has_bootstrap else None)
        self.scan_btn.pack(side=LEFT, padx=(0, 5))
        self.cancel_btn = _ttk.Button(bf, text="⏹ 停止", command=self._cancel_scan, state=DISABLED, bootstyle="danger" if _has_bootstrap else None)
        self.cancel_btn.pack(side=LEFT)

    def _build_progress(self, parent):
        """进度区"""
        f = _ttk.Frame(parent)
        f.pack(fill=X, pady=(0, 10))
        self.progress_var = tk.DoubleVar()
        self.progress_bar = _ttk.Progressbar(f, variable=self.progress_var, maximum=100, bootstyle="success-striped" if _has_bootstrap else None)
        self.progress_bar.pack(fill=X, side=LEFT, expand=True)
        self.status_var = tk.StringVar(value="就绪 - 请选择目录开始扫描")
        _ttk.Label(f, textvariable=self.status_var, width=50, anchor=W).pack(side=LEFT, padx=(10, 0))

    def _build_result_list(self, parent):
        """结果列表区"""
        outer = _ttk.LabelFrame(parent, text=" 扫描结果 ")
        outer.pack(fill=BOTH, expand=True, pady=(0, 10), padx=5)

        # 搜索框
        sf = _ttk.Frame(outer)
        sf.pack(fill=X, padx=8, pady=(8, 0))
        _ttk.Label(sf, text="🔍 搜索:").pack(side=LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        _ttk.Entry(sf, textvariable=self.search_var).pack(side=LEFT, fill=X, expand=True, padx=(5, 10))
        _ttk.Label(sf, text="输入关键词过滤结果", foreground="gray").pack(side=LEFT)

        # Treeview（添加修改时间列）
        lf = _ttk.Frame(outer, padding=8)
        lf.pack(fill=BOTH, expand=True)

        cols = ("select", "group", "size", "modified", "path", "hash")
        self.tree = _ttk.Treeview(lf, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("select", text="✓", anchor=CENTER)
        self.tree.heading("group", text="组号 ↕", anchor=CENTER, command=lambda: self._sort_tree("group"))
        self.tree.heading("size", text="大小 ↕", anchor=E, command=lambda: self._sort_tree("size"))
        self.tree.heading("modified", text="修改时间 ↕", anchor=CENTER, command=lambda: self._sort_tree("modified"))
        self.tree.heading("path", text="文件路径 ↕", anchor=W, command=lambda: self._sort_tree("path"))
        self.tree.heading("hash", text="哈希值", anchor=W)
        self.tree.column("select", width=40, minwidth=40, anchor=CENTER, stretch=False)
        self.tree.column("group", width=60, minwidth=50, anchor=CENTER, stretch=False)
        self.tree.column("size", width=90, minwidth=70, anchor=E, stretch=False)
        self.tree.column("modified", width=140, minwidth=120, anchor=CENTER, stretch=False)
        self.tree.column("path", width=400, minwidth=200)
        self.tree.column("hash", width=280, minwidth=200)

        sb = _ttk.Scrollbar(lf, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        lf.grid_rowconfigure(0, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        # 事件绑定
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)

        # 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0, font=("Microsoft YaHei UI", 9))
        self.context_menu.add_command(label="📄 打开文件", command=self._open_file)
        self.context_menu.add_command(label="📁 打开所在目录", command=self._open_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📋 复制路径", command=self._copy_path)
        self.context_menu.add_command(label="📋 复制文件名", command=self._copy_filename)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="ℹ️ 文件属性", command=self._show_file_properties)

        # 标签样式
        self.tree.tag_configure("original", background="#e8f5e9", foreground="#2e7d32")
        self.tree.tag_configure("duplicate", background="#fff8e1", foreground="#f57f17")

        # 快捷键
        self.root.bind("<Control-o>", lambda e: self._browse_dir())
        self.root.bind("<Control-s>", lambda e: self._start_scan())
        self.root.bind("<Control-e>", lambda e: self._export_results())
        self.root.bind("<Control-q>", lambda e: self._on_close())
        self.root.bind("<F1>", lambda e: self._show_help())
        self.root.bind("<F5>", lambda e: self._start_scan())
        self.root.bind("<Control-Shift-S>", lambda e: self._save_results())
        self.root.bind("<Control-Shift-O>", lambda e: self._load_results())

        # 拖放支持
        self._setup_drag_drop()

    def _setup_drag_drop(self):
        """设置拖放支持"""
        try:
            # 尝试使用 tkinterdnd2
            dnd = _init_tkdnd()
            if dnd and hasattr(self.root, 'drop_target_register'):
                self.root.drop_target_register(dnd.DND_FILES)
                self.root.dnd_bind('<<Drop>>', self._on_drop)
                logger.info("拖放支持已启用 (tkinterdnd2)")
                return
        except Exception as e:
            logger.debug(f"tkinterdnd2 不可用: {e}")

        # 回退：使用 Windows 原生拖放
        if sys.platform == 'win32':
            try:
                self.root.bind('<Drop>', self._on_drop_windows)
                logger.info("拖放支持已启用 (Windows 原生)")
            except Exception:
                logger.info("拖放支持不可用")
        else:
            logger.info("拖放支持不可用")

    def _on_drop(self, event):
        """处理拖放事件（tkinterdnd2）"""
        try:
            path = event.data.strip('{}')
            if os.path.isdir(path):
                self.dir_var.set(path)
                logger.info(f"拖放目录: {path}")
            elif os.path.isfile(path):
                self.dir_var.set(str(Path(path).parent))
                logger.info(f"拖放文件，使用父目录: {Path(path).parent}")
        except Exception as e:
            logger.error(f"处理拖放失败: {e}")

    def _on_drop_windows(self, event):
        """处理拖放事件（Windows 原生）"""
        try:
            # 从事件中获取文件路径
            path = event.data
            if path:
                path = path.strip('{}')
                if os.path.isdir(path):
                    self.dir_var.set(path)
                elif os.path.isfile(path):
                    self.dir_var.set(str(Path(path).parent))
        except Exception as e:
            logger.error(f"处理拖放失败: {e}")

    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件
        fm = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=fm)
        fm.add_command(label="📂 选择目录", command=self._browse_dir, accelerator="Ctrl+O")
        fm.add_separator()
        fm.add_command(label="💾 保存扫描结果", command=self._save_results, accelerator="Ctrl+Shift+S")
        fm.add_command(label="📂 加载扫描结果", command=self._load_results, accelerator="Ctrl+Shift+O")
        fm.add_separator()
        fm.add_command(label="📊 导出为 CSV", command=self._export_results, accelerator="Ctrl+E")
        fm.add_separator()
        fm.add_command(label="❌ 退出", command=self._on_close, accelerator="Ctrl+Q")

        # 视图
        vm = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=vm)

        # 深色模式
        self.dark_mode_var = tk.BooleanVar(value=False)
        vm.add_checkbutton(label="🌙 深色模式", variable=self.dark_mode_var, command=self._toggle_dark_mode)
        vm.add_separator()

        wm = tk.Menu(vm, tearoff=0)
        vm.add_cascade(label="窗口大小", menu=wm)
        for s in ["小", "中", "大"]:
            w, h = WINDOW_SIZES[s]
            wm.add_radiobutton(label=f"{s} ({w}×{h})", command=lambda x=s: self._change_window_size(x))
        fm2 = tk.Menu(vm, tearoff=0)
        vm.add_cascade(label="字体大小", menu=fm2)
        for s in ["小", "中", "大"]:
            fm2.add_radiobutton(label=s, command=lambda x=s: self._change_font_size(x))
        vm.add_separator()
        vm.add_command(label="恢复默认", command=self._reset_view)

        # 设置
        sm = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=sm)
        self.single_instance_var = tk.BooleanVar(value=self.config.single_instance)
        sm.add_checkbutton(label="🔒 单实例模式", variable=self.single_instance_var, command=self._on_single_instance_change)
        sm.add_separator()
        ptm = tk.Menu(sm, tearoff=0)
        sm.add_cascade(label="📁 文件类型过滤", menu=ptm)
        self.file_filter_var = tk.StringVar(value=self.config.file_filter)
        for name in FILE_FILTERS:
            ptm.add_radiobutton(label=name, variable=self.file_filter_var, value=name)
        sm.add_separator()
        self.sound_var = tk.BooleanVar(value=self.config.sound_enabled)
        sm.add_checkbutton(label="🔊 扫描完成提示音", variable=self.sound_var)

        # 帮助
        hm = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=hm)
        hm.add_command(label="📖 使用说明", command=self._show_help, accelerator="F1")
        hm.add_command(label="⌨️ 快捷键", command=self._show_shortcuts)
        hm.add_separator()
        hm.add_command(label="ℹ️ 关于", command=self._show_about)

    def _apply_config(self):
        """应用配置"""
        self.dir_var.set(self.config.last_dir)
        self.dir_combo['values'] = self.config.recent_dirs
        self.recursive_var.set(self.config.recursive)
        self.min_size_var.set(self.config.min_size)

        # 应用深色模式
        if self.config.dark_mode:
            self.dark_mode_var.set(True)
            self._toggle_dark_mode()

    # ==================== 配置 ====================

    def _save_config(self):
        """保存配置"""
        self.config.last_dir = self.dir_var.get()
        self.config.recursive = self.recursive_var.get()
        self.config.min_size = self.min_size_var.get()
        self.config.file_filter = self.file_filter_var.get()
        self.config.sound_enabled = self.sound_var.get()
        self.config.single_instance = self.single_instance_var.get()
        self.config.dark_mode = self.dark_mode_var.get()
        self.config.add_recent_dir(self.dir_var.get())
        self.config.save()

    def _on_close(self):
        """关闭窗口"""
        self._save_config()
        if not self.config.single_instance:
            try:
                lf = get_lock_file()
                if lf.exists():
                    lf.unlink()
            except OSError:
                pass
        self.root.destroy()

    def _on_single_instance_change(self):
        """切换单实例模式"""
        self._save_config()
        lf = get_lock_file()
        if self.single_instance_var.get():
            try:
                lf.parent.mkdir(parents=True, exist_ok=True)
                lf.write_text(str(os.getpid()))
            except OSError:
                pass
            messagebox.showinfo("设置", "单实例模式已开启")
        else:
            try:
                if lf.exists():
                    lf.unlink()
            except OSError:
                pass
            messagebox.showinfo("设置", "单实例模式已关闭")

    # ==================== 界面操作 ====================

    def _browse_dir(self):
        d = filedialog.askdirectory(title="选择要扫描的目录")
        if d:
            self.dir_var.set(d)

    def _change_window_size(self, size):
        w, h = WINDOW_SIZES.get(size, WINDOW_SIZES["中"])
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _change_font_size(self, size):
        c = FONT_SIZES.get(size, FONT_SIZES["中"])
        s = _ttk.Style()
        s.configure("Treeview", rowheight=c["row"], font=("Microsoft YaHei UI", c["tree"]))
        s.configure("Treeview.Heading", font=("Microsoft YaHei UI", c["tree"], "bold"))

    def _reset_view(self):
        self._change_window_size("中")
        self._change_font_size("中")

    def _toggle_dark_mode(self):
        """切换深色模式"""
        if not _has_bootstrap:
            # 没有 ttkbootstrap 时使用简单深色模式
            self._toggle_dark_mode_simple()
            return

        style = _ttk.Style()

        if self.dark_mode_var.get():
            # 使用 ttkbootstrap 的 darkly 主题
            style.theme_use("darkly")
            # Treeview 深色样式
            style.configure("Treeview",
                            background="#2b2b2b",
                            foreground="#ffffff",
                            fieldbackground="#2b2b2b",
                            rowheight=28,
                            font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading",
                            font=("Microsoft YaHei UI", 9, "bold"))
            style.map("Treeview",
                      background=[("selected", "#0d6efd")],
                      foreground=[("selected", "#ffffff")])
            # 标签颜色
            self.tree.tag_configure("original", background="#1a3a1a", foreground="#4caf50")
            self.tree.tag_configure("duplicate", background="#3a2a1a", foreground="#ff9800")
        else:
            # 恢复浅色主题
            style.theme_use("litera")
            style.configure("Treeview",
                            rowheight=28,
                            font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading",
                            font=("Microsoft YaHei UI", 9, "bold"))
            # 标签颜色
            self.tree.tag_configure("original", background="#e8f5e9", foreground="#2e7d32")
            self.tree.tag_configure("duplicate", background="#fff8e1", foreground="#f57f17")

    def _toggle_dark_mode_simple(self):
        """简单深色模式（无 ttkbootstrap）"""
        style = _ttk.Style()

        if self.dark_mode_var.get():
            bg = "#1e1e1e"
            fg = "#d4d4d4"
            field_bg = "#252526"
            select_bg = "#264f78"

            style.theme_use("clam")
            style.configure(".", background=bg, foreground=fg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TButton", background="#333333", foreground=fg)
            style.configure("Treeview", background=field_bg, foreground=fg, fieldbackground=field_bg)
            style.configure("Treeview.Heading", background="#333333", foreground=fg)
            style.map("Treeview", background=[("selected", select_bg)])

            self.tree.tag_configure("original", background="#1a3a1a", foreground="#4caf50")
            self.tree.tag_configure("duplicate", background="#3a2a1a", foreground="#ff9800")
        else:
            style.theme_use("clam")
            style.configure("Treeview",
                            rowheight=28,
                            font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading",
                            font=("Microsoft YaHei UI", 9, "bold"))

            self.tree.tag_configure("original", background="#e8f5e9", foreground="#2e7d32")
            self.tree.tag_configure("duplicate", background="#fff8e1", foreground="#f57f17")

    def _focus_search(self):
        def find(w):
            if isinstance(w, _ttk.Entry):
                try:
                    if str(w.cget("textvariable")) == str(self.search_var):
                        w.focus_set()
                        return True
                except Exception:
                    pass
            for c in w.winfo_children():
                if find(c):
                    return True
            return False
        find(self.root)

    # ==================== 扫描 ====================

    def _start_scan(self):
        d = self.dir_var.get().strip()
        if not d or not os.path.isdir(d):
            messagebox.showerror("错误", "请选择有效的目录")
            return
        if self.scanning:
            return

        self.scanning = True
        self.scan_btn.configure(state=DISABLED)
        self.cancel_btn.configure(state=NORMAL)
        self.delete_btn.configure(state=DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.selected_files.clear()
        self.scan_result = None
        self.info_var.set("")
        self.search_var.set("")

        import threading
        threading.Thread(target=self._scan_worker, args=(d,), daemon=True).start()

    def _cancel_scan(self):
        self.scanner.cancel()
        self.cancel_btn.configure(state=DISABLED)
        self._update_status("正在取消...")

    def _scan_worker(self, directory):
        try:
            min_size = 0
            try:
                min_size = int(self.min_size_var.get())
            except ValueError:
                pass

            result = self.scanner.scan(
                directory=directory,
                recursive=self.recursive_var.get(),
                min_size=min_size,
                file_extensions=self.config.get_filter_extensions(),
                progress_callback=self._on_progress
            )
            self.root.after(0, lambda: self._display_results(result))
        except FileNotFoundError as e:
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        except PermissionError as e:
            self.root.after(0, lambda: messagebox.showerror("权限错误", f"无权限访问: {e}"))
        except Exception as e:
            logger.exception("扫描异常")
            self.root.after(0, lambda: messagebox.showerror("错误", f"扫描出错: {type(e).__name__}"))
        finally:
            self.scanning = False
            self.root.after(0, self._reset_buttons)

    def _on_progress(self, status, current, total):
        if total > 0:
            self.root.after(0, lambda: self.progress_var.set(current / total * 100))
        self.root.after(0, lambda: self.status_var.set(status))

    def _reset_buttons(self):
        self.scan_btn.configure(state=NORMAL)
        self.cancel_btn.configure(state=DISABLED)
        if not self.scan_result or not self.scan_result.duplicates:
            self.delete_btn.configure(state=DISABLED)

    def _display_results(self, result):
        self.scan_result = result
        self.tree.delete(*self.tree.get_children())
        self.selected_files.clear()

        if not result.duplicates:
            self.info_var.set("✨ 未发现重复文件")
            self._update_status("✅ 扫描完成，未发现重复文件")
            self.progress_var.set(100)
            if self.sound_var.get():
                self.root.bell()
            return

        self._update_status(f"✅ 扫描完成: {len(result.duplicates)} 组重复")
        self.progress_var.set(100)
        if self.sound_var.get():
            self.root.bell()

        self.tree.configure(selectmode="none")
        for i, (h, files, size) in enumerate(result.duplicates, 1):
            for j, fp in enumerate(files):
                tag = "original" if j == 0 else "duplicate"
                # 获取文件修改时间
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")
                except (OSError, ValueError):
                    mtime = "-"
                self.tree.insert("", END, values=("⬜" if j == 0 else "☐", f"#{i}", format_size(size), mtime, fp, h), tags=(tag,))
        self.tree.configure(selectmode="extended")

        self._select_second()
        self.info_var.set(f"📊 共 {len(result.duplicates)} 组重复，{result.total_duplicates} 个文件，可释放 {format_size(result.total_wasted)}")
        self.delete_btn.configure(state=NORMAL)

    # ==================== 结果操作 ====================

    def _on_search_change(self, *args):
        if self._search_timer:
            self.root.after_cancel(self._search_timer)
        self._search_timer = self.root.after(300, self._do_search)

    def _do_search(self):
        kw = self.search_var.get().lower().strip()
        if not kw:
            for item in self.tree.get_children():
                self.tree.reattach(item, "", END)
            return
        for item in self.tree.get_children():
            v = self.tree.item(item, "values")
            # path 在第 4 列（索引 4），hash 在第 5 列（索引 5）
            if kw in str(v[4]).lower() or kw in str(v[5]).lower():
                self.tree.reattach(item, "", END)
            else:
                self.tree.detach(item)

    def _sort_tree(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        items = [(self.tree.set(item, col), item) for item in self.tree.get_children()]
        if col == "size":
            def ps(s):
                p = s.split()
                if len(p) == 2:
                    return float(p[0]) * {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}.get(p[1], 1)
                return 0
            items.sort(key=lambda x: ps(x[0]), reverse=self.sort_reverse)
        elif col == "group":
            items.sort(key=lambda x: int(x[0].replace("#", "")), reverse=self.sort_reverse)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=self.sort_reverse)

        for i, (_, item) in enumerate(items):
            self.tree.move(item, "", i)

        for c in ["group", "size", "path"]:
            t = self.tree.heading(c, "text").replace(" ↑", "").replace(" ↓", "")
            if c == col:
                t += " ↓" if self.sort_reverse else " ↑"
            self.tree.heading(c, text=t)

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if not row or col != "#1":
            return
        # path 在第 4 列（索引 4）
        fp = self.tree.item(row, "values")[4]
        if fp in self.selected_files:
            self.selected_files.discard(fp)
            self.tree.set(row, "select", "☐")
        else:
            self.selected_files.add(fp)
            self.tree.set(row, "select", "☑")

    def _on_double_click(self, event):
        fp = self._get_clicked_filepath(event)
        if fp and os.path.exists(fp):
            self._open_file_path(fp)

    def _show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.context_menu.post(event.x_root, event.y_root)

    def _get_clicked_filepath(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        v = self.tree.item(row, "values")
        # path 在第 4 列（索引 4）
        return v[4] if v and len(v) > 4 else None

    def _get_selected_filepath(self):
        sel = self.tree.selection()
        if not sel:
            return None
        v = self.tree.item(sel[0], "values")
        # path 在第 4 列（索引 4）
        return v[4] if v and len(v) > 4 else None

    def _open_file(self):
        fp = self._get_selected_filepath()
        if fp:
            self._open_file_path(fp)

    def _open_folder(self):
        fp = self._get_selected_filepath()
        if fp:
            self._open_folder_path(fp)

    def _copy_path(self):
        fp = self._get_selected_filepath()
        if fp:
            self.root.clipboard_clear()
            self.root.clipboard_append(fp)
            self._update_status("📋 已复制路径")

    def _copy_filename(self):
        """复制文件名到剪贴板"""
        fp = self._get_selected_filepath()
        if fp:
            self.root.clipboard_clear()
            self.root.clipboard_append(Path(fp).name)
            self._update_status("📋 已复制文件名")

    def _show_file_properties(self):
        """显示文件属性对话框"""
        # 获取选中的文件路径
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个文件", parent=self.root)
            return

        item = sel[0]
        values = self.tree.item(item, "values")
        if not values or len(values) < 5:
            messagebox.showwarning("提示", "无法获取文件信息", parent=self.root)
            return

        fp = values[4]  # path 在第 4 列

        # 显示文件属性
        try:
            stat = os.stat(fp)
            size = format_size(stat.st_size)
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            ctime = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")

            # 创建对话框
            dlg = tk.Toplevel(self.root)
            dlg.title("文件属性")
            dlg.transient(self.root)
            dlg.grab_set()

            # 主框架
            main_frame = tk.Frame(dlg, padx=20, pady=15)
            main_frame.pack(fill=BOTH, expand=True)

            # 文件信息（使用 Label 自适应）
            tk.Label(main_frame, text="📄 文件属性", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor=W, pady=(0, 15))

            # 信息网格
            info_frame = tk.Frame(main_frame)
            info_frame.pack(fill=X)

            row = 0
            for label_text, value in [
                ("路径:", fp),
                ("文件名:", Path(fp).name),
                ("大小:", f"{size} ({stat.st_size:,} 字节)"),
                ("修改时间:", mtime),
                ("创建时间:", ctime),
            ]:
                tk.Label(info_frame, text=label_text, font=("Microsoft YaHei UI", 10, "bold")).grid(row=row, column=0, sticky=W, pady=2)
                tk.Label(info_frame, text=value, font=("Microsoft YaHei UI", 10)).grid(row=row, column=1, sticky=W, padx=(10, 0), pady=2)
                row += 1

            # 按钮
            tk.Button(main_frame, text="确定", command=dlg.destroy, width=10).pack(pady=(15, 0))

            # 自适应大小
            dlg.update_idletasks()
            w = dlg.winfo_reqwidth() + 40
            h = dlg.winfo_reqheight() + 20
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
            dlg.geometry(f"{w}x{h}+{x}+{y}")

        except OSError as e:
            messagebox.showerror("错误", f"无法获取文件属性:\n{e}", parent=self.root)

    def _open_file_path(self, fp):
        try:
            if os.name == 'nt':
                os.startfile(fp)
            elif sys.platform == 'darwin':
                subprocess.run(['open', fp], check=True)
            else:
                subprocess.run(['xdg-open', fp], check=True)
        except Exception as e:
            logger.error(f"打开文件失败: {fp} - {e}")
            messagebox.showerror("错误", f"无法打开文件: {type(e).__name__}")

    def _open_folder_path(self, fp):
        try:
            if os.name == 'nt':
                # Windows explorer /select 即使成功也返回非零退出码，不用 check=True
                subprocess.run(['explorer', '/select,', fp])
            elif sys.platform == 'darwin':
                subprocess.run(['open', '-R', fp], check=True)
            else:
                subprocess.run(['xdg-open', str(Path(fp).parent)], check=True)
        except Exception as e:
            logger.error(f"打开目录失败: {fp} - {e}")
            messagebox.showerror("错误", f"无法打开目录: {type(e).__name__}")

    def _select_second(self):
        self.selected_files.clear()
        if self.scan_result:
            for _, files, _ in self.scan_result.duplicates:
                self.selected_files.update(files[1:])
        self._refresh_checks()

    def _invert_selection(self):
        all_f = set()
        if self.scan_result:
            for _, files, _ in self.scan_result.duplicates:
                all_f.update(files[1:])
        self.selected_files = all_f - self.selected_files
        self._refresh_checks()

    def _clear_selection(self):
        self.selected_files.clear()
        self._refresh_checks()

    def _refresh_checks(self):
        orig = set()
        if self.scan_result:
            for _, files, _ in self.scan_result.duplicates:
                orig.add(files[0])
        for item in self.tree.get_children():
            # path 在第 4 列（索引 4）
            fp = self.tree.item(item, "values")[4]
            self.tree.set(item, "select", "☑" if fp in self.selected_files else ("⬜" if fp in orig else "☐"))

    # ==================== 删除 ====================

    def _delete_selected(self):
        if not self.selected_files:
            messagebox.showinfo("提示", "请先选择要删除的文件")
            return

        if self.scan_result:
            for i, (_, files, _) in enumerate(self.scan_result.duplicates, 1):
                if not [f for f in files if f not in self.selected_files]:
                    messagebox.showwarning("警告", f"第 #{i} 组的所有文件都被选中\n请至少保留一个")
                    return

        files = sorted(self.selected_files)
        total = 0
        for f in files:
            try:
                total += os.path.getsize(f)
            except OSError:
                pass

        use_trash = False
        if is_send2trash_available():
            use_trash = messagebox.askyesno("删除方式", f"删除 {len(files)} 个文件？\n释放: {format_size(total)}\n\n是=回收站 否=永久删除")
        else:
            if not messagebox.askyesno("确认", f"永久删除 {len(files)} 个文件？\n释放: {format_size(total)}\n\n⚠️ 不可撤销！"):
                return

        ok, fail, errs = 0, 0, []
        for f in files:
            try:
                if use_trash:
                    import send2trash
                    send2trash.send2trash(f)
                else:
                    os.remove(f)
                ok += 1
            except Exception as e:
                fail += 1
                errs.append(f"{Path(f).name}: {e}")
                logger.error(f"删除失败: {f} - {e}")

        msg = f"{'移到回收站' if use_trash else '永久删除'}完成\n成功: {ok} 失败: {fail}"
        if errs:
            msg += "\n\n" + "\n".join(errs[:5])
        messagebox.showinfo("完成", msg)

        if ok > 0:
            self._start_scan()

    # ==================== 导出 ====================

    def _export_results(self):
        if not self.scan_result or not self.scan_result.duplicates:
            messagebox.showinfo("提示", "没有可导出的结果")
            return

        fp = filedialog.asksaveasfilename(title="导出", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not fp:
            return

        try:
            with open(fp, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(["组号", "大小", "哈希", "路径", "选中"])
                for i, (h, files, size) in enumerate(self.scan_result.duplicates, 1):
                    for p in files:
                        w.writerow([f"#{i}", format_size(size), h, p, "是" if p in self.selected_files else "否"])
            messagebox.showinfo("成功", f"已导出到:\n{fp}")
        except Exception as e:
            logger.error(f"导出失败: {e}")
            messagebox.showerror("错误", f"导出失败: {e}")

    def _save_results(self):
        """保存扫描结果为 JSON"""
        if not self.scan_result or not self.scan_result.duplicates:
            messagebox.showinfo("提示", "没有可保存的扫描结果")
            return

        fp = filedialog.asksaveasfilename(
            title="保存扫描结果",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("所有文件", "*.*")]
        )
        if not fp:
            return

        try:
            import json
            data = {
                "version": __version__,
                "duplicates": [
                    {"hash": h, "files": files, "size": size}
                    for h, files, size in self.scan_result.duplicates
                ],
                "total_scanned": self.scan_result.total_scanned,
                "total_duplicates": self.scan_result.total_duplicates,
                "total_wasted": self.scan_result.total_wasted,
                "selected": list(self.selected_files)
            }
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"扫描结果已保存到:\n{fp}")
        except Exception as e:
            logger.error(f"保存失败: {e}")
            messagebox.showerror("错误", f"保存失败: {e}")

    def _load_results(self):
        """加载扫描结果"""
        fp = filedialog.askopenfilename(
            title="加载扫描结果",
            filetypes=[("JSON", "*.json"), ("所有文件", "*.*")]
        )
        if not fp:
            return

        try:
            import json
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 重建 ScanResult
            from .scanner import ScanResult
            result = ScanResult()
            for item in data.get("duplicates", []):
                result.duplicates.append((item["hash"], item["files"], item["size"]))
            result.total_scanned = data.get("total_scanned", 0)
            result.total_duplicates = data.get("total_duplicates", 0)
            result.total_wasted = data.get("total_wasted", 0)

            # 恢复选中状态
            self.selected_files = set(data.get("selected", []))

            # 显示结果
            self._display_results(result)

            # 恢复选中状态的显示
            self._refresh_checks()

            messagebox.showinfo("成功", f"已加载扫描结果:\n{fp}")
        except Exception as e:
            logger.error(f"加载失败: {e}")
            messagebox.showerror("错误", f"加载失败: {e}")

    # ==================== 帮助 ====================

    def _show_help(self):
        win = tk.Toplevel(self.root)
        win.title("使用说明")
        win.transient(self.root)

        # 居中显示
        w, h = 600, 650
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

        t = tk.Text(win, wrap=tk.WORD, padx=20, pady=20, font=("Microsoft YaHei UI", 11))
        t.pack(fill=tk.BOTH, expand=True)
        t.insert(tk.END, f"""📖 使用说明 (v{__version__})

1. 选择目录
   点击「浏览」或从下拉列表选择最近目录
   也可以直接拖放文件夹到窗口

2. 设置选项
   • 递归子目录：是否扫描子文件夹
   • 最小文件大小：忽略小于此大小的文件
   • 文件类型：设置 → 文件类型过滤

3. 开始扫描
   点击「🔍 开始扫描」或按 Ctrl+S

4. 查看结果
   • 绿色行：每组第一个文件（建议保留）
   • 橙色行：重复文件（建议删除）
   • 双击打开预览，右键更多操作
   • 点击列头可排序

5. 删除文件
   扫描自动选中推荐删除的文件
   点击「🗑️ 删除选中」确认

6. 保存/加载结果
   • Ctrl+Shift+S 保存扫描结果
   • Ctrl+Shift+O 加载之前的扫描结果

7. 深色模式
   视图 → 深色模式""")
        t.configure(state=tk.DISABLED)

    def _show_shortcuts(self):
        win = tk.Toplevel(self.root)
        win.title("快捷键")
        win.transient(self.root)
        win.grab_set()

        # 居中显示
        w, h = 400, 350
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

        frame = tk.Frame(win, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="⌨️ 快捷键", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor=tk.W, pady=(0, 15))

        shortcuts = [
            ("Ctrl+O", "选择目录"),
            ("Ctrl+S", "开始扫描"),
            ("Ctrl+E", "导出为 CSV"),
            ("Ctrl+Shift+S", "保存扫描结果"),
            ("Ctrl+Shift+O", "加载扫描结果"),
            ("Ctrl+Q", "退出"),
            ("F1", "帮助"),
            ("F5", "刷新扫描"),
        ]

        for key, desc in shortcuts:
            row = tk.Frame(frame)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=key, font=("Consolas", 11), width=15, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=desc, font=("Microsoft YaHei UI", 11)).pack(side=tk.LEFT)

    def _show_about(self):
        win = tk.Toplevel(self.root)
        win.title("关于")
        win.transient(self.root)
        win.grab_set()

        # 居中显示
        w, h = 500, 400
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

        frame = tk.Frame(win, padx=30, pady=30)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="🔍 Duplicate Cleaner", font=("Microsoft YaHei UI", 20, "bold")).pack(pady=(0, 15))
        tk.Label(frame, text=f"v{__version__}", font=("Microsoft YaHei UI", 14)).pack()
        tk.Label(frame, text="\n重复文件清理工具\n基于文件内容哈希精准识别\n支持图形界面和命令行两种模式", font=("Microsoft YaHei UI", 12)).pack(pady=(10, 0))
        tk.Label(frame, text="Python + tkinter + ttkbootstrap", font=("Microsoft YaHei UI", 11), fg="gray").pack(pady=(20, 0))
        tk.Label(frame, text="作者: Kanji", font=("Microsoft YaHei UI", 11), fg="gray").pack(pady=(5, 0))

    # ==================== 工具 ====================

    def _update_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))


def main():
    """GUI 主入口"""
    _init_ttk()

    if _has_bootstrap:
        root = _ttk.Window(title=f"Duplicate Cleaner v{__version__}", themename="litera", size=(1300, 800), minsize=(1000, 600))
    else:
        root = tk.Tk()

    DuplicateCleanerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
