"""
图形界面模块

使用 tkinter + ttkbootstrap 构建的现代 GUI。
所有业务逻辑委托给 scanner 和 config 模块。

模块职责：
- 界面布局和样式
- 用户交互事件处理
- 扫描结果展示
- 文件操作确认
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

from . import __version__
from .config import AppConfig, FONT_SIZES, WINDOW_SIZES, FILE_FILTERS
from .scanner import FileScanner, ScanResult
from .utils import format_size, is_send2trash_available, get_lock_file

logger = logging.getLogger("duplicate_cleaner")

# tkinter 常量别名
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

# ttkbootstrap 延迟初始化
_ttk = None
_has_bootstrap = False


def _init_ttk():
    """延迟导入 ttkbootstrap，加快启动速度"""
    global _ttk, _has_bootstrap
    if _ttk is not None:
        return
    try:
        import ttkbootstrap as tb
        _ttk = tb
        _has_bootstrap = True
        logger.info("使用 ttkbootstrap 主题")
    except ImportError:
        from tkinter import ttk as tb
        _ttk = tb
        _has_bootstrap = False
        logger.info("ttkbootstrap 未安装，使用默认主题")


class DuplicateCleanerGUI:
    """
    重复文件清理工具 GUI 主类

    职责：
    - 构建界面布局
    - 处理用户交互
    - 展示扫描结果
    - 管理文件删除操作

    使用示例：
        root = tk.Tk()
        app = DuplicateCleanerGUI(root)
        root.mainloop()
    """

    def __init__(self, root):
        """
        初始化 GUI

        Args:
            root: tkinter 根窗口
        """
        _init_ttk()

        self.root = root
        self.root.title(f"Duplicate Cleaner v{__version__}")
        self.root.geometry("1300x800")
        self.root.minsize(1000, 600)

        # 核心组件
        self.config = AppConfig.load()
        self.scanner = FileScanner()

        # 扫描结果
        self.scan_result: Optional[ScanResult] = None
        self.selected_files: set = set()

        # 扫描状态
        self.scanning = False

        # 排序状态
        self.sort_column = None
        self.sort_reverse = False

        # 搜索防抖定时器
        self._search_timer = None

        # 初始化界面
        self._setup_style()
        self._build_ui()
        self._create_menu()
        self._apply_config()

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        logger.info("GUI 初始化完成")

    def _setup_style(self):
        """配置界面样式"""
        style = _ttk.Style()

        if _has_bootstrap:
            style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        else:
            style.theme_use("clam")
            style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
            style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self):
        """构建界面布局"""
        main_frame = _ttk.Frame(self.root)
        main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # === 底部区域（先放，固定在底部） ===
        self._build_bottom(main_frame)

        # === 顶部标题 ===
        self._build_header(main_frame)

        # === 扫描配置区 ===
        self._build_config(main_frame)

        # === 进度区 ===
        self._build_progress(main_frame)

        # === 结果列表区 ===
        self._build_result_list(main_frame)

    def _build_bottom(self, parent):
        """构建底部操作区"""
        # 状态栏
        status_frame = _ttk.Frame(parent)
        status_frame.pack(fill=X, side=BOTTOM, pady=(4, 0))

        self.status_detail_var = tk.StringVar(value="就绪")
        _ttk.Label(status_frame, textvariable=self.status_detail_var,
                   font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=LEFT)
        _ttk.Label(status_frame, text="Ctrl+O 打开 | Ctrl+S 扫描 | F1 帮助",
                   font=("Microsoft YaHei UI", 8), foreground="gray").pack(side=RIGHT)

        # 操作按钮区
        action_frame = _ttk.Frame(parent)
        action_frame.pack(fill=X, side=BOTTOM, pady=(4, 0))

        # 统计信息
        self.info_var = tk.StringVar(value="")
        _ttk.Label(action_frame, textvariable=self.info_var,
                   font=("Microsoft YaHei UI", 9)).pack(side=LEFT)

        # 按钮组
        btn_frame = _ttk.Frame(action_frame)
        btn_frame.pack(side=RIGHT)

        # 删除按钮
        self.delete_btn = _ttk.Button(
            btn_frame, text="🗑️ 删除选中",
            command=self._delete_selected, state=DISABLED,
            bootstyle="danger" if _has_bootstrap else None
        )
        self.delete_btn.pack(side=RIGHT, padx=(8, 0))

        _ttk.Button(btn_frame, text="取消选择", command=self._clear_selection).pack(side=RIGHT, padx=2)
        _ttk.Button(btn_frame, text="反选", command=self._invert_selection).pack(side=RIGHT, padx=2)
        _ttk.Button(btn_frame, text="全选重复", command=self._select_second).pack(side=RIGHT, padx=2)

        _ttk.Separator(btn_frame, orient=VERTICAL).pack(side=RIGHT, fill=Y, padx=6)

        _ttk.Button(btn_frame, text="📊 导出", command=self._export_results).pack(side=RIGHT, padx=2)
        _ttk.Button(btn_frame, text="🔍 搜索", command=self._focus_search).pack(side=RIGHT, padx=2)

    def _build_header(self, parent):
        """构建标题区"""
        header = _ttk.Frame(parent)
        header.pack(fill=X, pady=(0, 10))

        _ttk.Label(header, text="🔍 Duplicate Cleaner",
                   font=("Microsoft YaHei UI", 18, "bold")).pack(side=LEFT)
        _ttk.Label(header, text="智能重复文件查找与清理",
                   font=("Microsoft YaHei UI", 10), foreground="gray").pack(side=LEFT, padx=(10, 0), pady=(5, 0))

    def _build_config(self, parent):
        """构建扫描配置区"""
        outer = _ttk.LabelFrame(parent, text=" 扫描配置 ")
        outer.pack(fill=X, pady=(0, 10), padx=5)
        frame = _ttk.Frame(outer, padding=12)
        frame.pack(fill=X)

        # 目录选择行
        dir_frame = _ttk.Frame(frame)
        dir_frame.pack(fill=X, pady=(0, 8))

        _ttk.Label(dir_frame, text="目录:", width=6).pack(side=LEFT)
        self.dir_var = tk.StringVar()
        self.dir_combo = _ttk.Combobox(dir_frame, textvariable=self.dir_var)
        self.dir_combo.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        _ttk.Button(dir_frame, text="📂 浏览", command=self._browse_dir,
                    bootstyle="outline" if _has_bootstrap else None).pack(side=LEFT)

        # 选项行
        opt_frame = _ttk.Frame(frame)
        opt_frame.pack(fill=X)

        self.recursive_var = tk.BooleanVar(value=True)
        _ttk.Checkbutton(opt_frame, text="递归子目录", variable=self.recursive_var).pack(side=LEFT)

        _ttk.Label(opt_frame, text="最小:").pack(side=LEFT, padx=(15, 5))
        self.min_size_var = tk.StringVar(value="0")
        _ttk.Entry(opt_frame, textvariable=self.min_size_var, width=8).pack(side=LEFT)
        _ttk.Label(opt_frame, text="字节").pack(side=LEFT, padx=(2, 0))

        # 扫描按钮
        btn_frame = _ttk.Frame(opt_frame)
        btn_frame.pack(side=RIGHT)

        self.scan_btn = _ttk.Button(btn_frame, text="🔍 开始扫描", command=self._start_scan,
                                    bootstyle="success" if _has_bootstrap else None)
        self.scan_btn.pack(side=LEFT, padx=(0, 5))

        self.cancel_btn = _ttk.Button(btn_frame, text="⏹ 停止", command=self._cancel_scan,
                                      state=DISABLED, bootstyle="danger" if _has_bootstrap else None)
        self.cancel_btn.pack(side=LEFT)

    def _build_progress(self, parent):
        """构建进度区"""
        frame = _ttk.Frame(parent)
        frame.pack(fill=X, pady=(0, 10))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = _ttk.Progressbar(
            frame, variable=self.progress_var, maximum=100,
            bootstyle="success-striped" if _has_bootstrap else None
        )
        self.progress_bar.pack(fill=X, side=LEFT, expand=True)

        self.status_var = tk.StringVar(value="就绪 - 请选择目录开始扫描")
        _ttk.Label(frame, textvariable=self.status_var, width=50, anchor=W).pack(side=LEFT, padx=(10, 0))

    def _build_result_list(self, parent):
        """构建结果列表区"""
        outer = _ttk.LabelFrame(parent, text=" 扫描结果 ")
        outer.pack(fill=BOTH, expand=True, pady=(0, 10), padx=5)

        # 搜索框
        search_frame = _ttk.Frame(outer)
        search_frame.pack(fill=X, padx=8, pady=(8, 0))
        _ttk.Label(search_frame, text="🔍 搜索:").pack(side=LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        _ttk.Entry(search_frame, textvariable=self.search_var).pack(side=LEFT, fill=X, expand=True, padx=(5, 10))
        _ttk.Label(search_frame, text="输入关键词过滤结果", foreground="gray").pack(side=LEFT)

        # Treeview
        list_frame = _ttk.Frame(outer, padding=8)
        list_frame.pack(fill=BOTH, expand=True)

        columns = ("select", "group", "size", "path", "hash")
        self.tree = _ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")

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

        scrollbar = _ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
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

    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="📂 选择目录", command=self._browse_dir, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="📊 导出扫描结果", command=self._export_results, accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="❌ 退出", command=self._on_close, accelerator="Ctrl+Q")

        # 视图菜单
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=view_menu)

        window_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="窗口大小", menu=window_menu)
        for size in ["小", "中", "大"]:
            w, h = WINDOW_SIZES[size]
            window_menu.add_radiobutton(
                label=f"{size}  ({w}×{h})", variable=self.config, value=size,
                command=lambda s=size: self._change_window_size(s)
            )

        font_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="字体大小", menu=font_menu)
        for size in ["小", "中", "大"]:
            font_menu.add_radiobutton(
                label=size, variable=self.config, value=size,
                command=lambda s=size: self._change_font_size(s)
            )

        view_menu.add_separator()
        view_menu.add_command(label="恢复默认", command=self._reset_view)

        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)

        self.single_instance_var = tk.BooleanVar(value=self.config.single_instance)
        settings_menu.add_checkbutton(
            label="🔒 单实例模式（只允许一个窗口）",
            variable=self.single_instance_var,
            command=self._on_single_instance_change
        )

        settings_menu.add_separator()
        filter_menu = tk.Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="📁 文件类型过滤", menu=filter_menu)
        self.file_filter_var = tk.StringVar(value=self.config.file_filter)
        for name in FILE_FILTERS.keys():
            filter_menu.add_radiobutton(label=name, variable=self.file_filter_var, value=name)

        settings_menu.add_separator()
        self.sound_var = tk.BooleanVar(value=self.config.sound_enabled)
        settings_menu.add_checkbutton(label="🔊 扫描完成提示音", variable=self.sound_var)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="📖 使用说明", command=self._show_help, accelerator="F1")
        help_menu.add_command(label="⌨️ 快捷键", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="ℹ️ 关于", command=self._show_about)

    def _apply_config(self):
        """应用加载的配置到界面"""
        self.dir_var.set(self.config.last_dir)
        self.dir_combo['values'] = self.config.recent_dirs
        self.recursive_var.set(self.config.recursive)
        self.min_size_var.set(self.config.min_size)

    # ==================== 配置操作 ====================

    def _save_current_config(self):
        """将当前界面状态保存到配置"""
        self.config.last_dir = self.dir_var.get()
        self.config.recursive = self.recursive_var.get()
        self.config.min_size = self.min_size_var.get()
        self.config.file_filter = self.file_filter_var.get()
        self.config.sound_enabled = self.sound_var.get()
        self.config.single_instance = self.single_instance_var.get()
        self.config.add_recent_dir(self.dir_var.get())
        self.config.save()

    def _on_close(self):
        """关闭窗口事件处理"""
        self._save_current_config()

        # 如果关闭单实例模式，删除锁文件
        if not self.config.single_instance:
            lock_file = get_lock_file()
            try:
                if lock_file.exists():
                    lock_file.unlink()
            except OSError as e:
                logger.warning(f"删除锁文件失败: {e}")

        self.root.destroy()

    def _on_single_instance_change(self):
        """单实例模式切换"""
        self._save_current_config()

        if self.single_instance_var.get():
            lock_file = get_lock_file()
            try:
                lock_file.parent.mkdir(parents=True, exist_ok=True)
                with open(lock_file, 'w') as f:
                    f.write(str(os.getpid()))
            except OSError as e:
                logger.warning(f"写入锁文件失败: {e}")
            messagebox.showinfo("设置已保存", "单实例模式已开启\n再次启动将跳转到此窗口")
        else:
            lock_file = get_lock_file()
            try:
                if lock_file.exists():
                    lock_file.unlink()
            except OSError as e:
                logger.warning(f"删除锁文件失败: {e}")
            messagebox.showinfo("设置已保存", "单实例模式已关闭\n现在可以直接启动新窗口")

    # ==================== 界口操作 ====================

    def _browse_dir(self):
        """选择目录"""
        dirpath = filedialog.askdirectory(title="选择要扫描的目录")
        if dirpath:
            self.dir_var.set(dirpath)

    def _change_window_size(self, size: str):
        """切换窗口大小"""
        w, h = WINDOW_SIZES.get(size, WINDOW_SIZES["中"])
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _change_font_size(self, size: str):
        """切换字体大小"""
        config = FONT_SIZES.get(size, FONT_SIZES["中"])
        style = _ttk.Style()
        style.configure("Treeview", rowheight=config["row"], font=("Microsoft YaHei UI", config["tree"]))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", config["tree"], "bold"))

    def _reset_view(self):
        """恢复默认视图"""
        self._change_window_size("中")
        self._change_font_size("中")

    def _focus_search(self):
        """聚焦搜索框"""
        # 递归查找搜索框
        def find_entry(widget):
            if isinstance(widget, _ttk.Entry):
                try:
                    if str(widget.cget("textvariable")) == str(self.search_var):
                        widget.focus_set()
                        return True
                except:
                    pass
            for child in widget.winfo_children():
                if find_entry(child):
                    return True
            return False

        find_entry(self.root)

    # ==================== 扫描操作 ====================

    def _start_scan(self):
        """开始扫描"""
        directory = self.dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
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
        thread = threading.Thread(target=self._scan_worker, args=(directory,), daemon=True)
        thread.start()

    def _cancel_scan(self):
        """取消扫描"""
        self.scanner.cancel()
        self.cancel_btn.configure(state=DISABLED)
        self._update_status("正在取消...")

    def _scan_worker(self, directory: str):
        """扫描工作线程"""
        try:
            result = self.scanner.scan(
                directory=directory,
                recursive=self.recursive_var.get(),
                min_size=self._get_min_size(),
                file_extensions=self.config.get_filter_extensions(),
                progress_callback=self._on_scan_progress
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

    def _get_min_size(self) -> int:
        """获取最小文件大小设置"""
        try:
            return int(self.min_size_var.get())
        except ValueError:
            return 0

    def _on_scan_progress(self, status: str, current: int, total: int):
        """扫描进度回调"""
        if total > 0:
            progress = current / total * 100
            self.root.after(0, lambda: self._update_progress(progress))
        self.root.after(0, lambda: self._update_status(status))

    def _reset_buttons(self):
        """重置按钮状态"""
        self.scan_btn.configure(state=NORMAL)
        self.cancel_btn.configure(state=DISABLED)
        if not self.scan_result or not self.scan_result.duplicates:
            self.delete_btn.configure(state=DISABLED)

    def _display_results(self, result: ScanResult):
        """显示扫描结果"""
        self.scan_result = result
        self.tree.delete(*self.tree.get_children())
        self.selected_files.clear()

        if not result.duplicates:
            self.info_var.set("✨ 未发现重复文件")
            self._update_status("✅ 扫描完成，未发现重复文件")
            self._update_progress(100)
            if self.sound_var.get():
                self.root.bell()
            return

        self._update_status(f"✅ 扫描完成: {len(result.duplicates)} 组重复")
        self._update_progress(100)

        if self.sound_var.get():
            self.root.bell()

        # 批量插入
        self.tree.configure(selectmode="none")

        for i, (file_hash, files, size) in enumerate(result.duplicates, 1):
            for j, filepath in enumerate(files):
                select_mark = "⬜" if j == 0 else "☐"
                tag = "original" if j == 0 else "duplicate"
                self.tree.insert("", END, values=(
                    select_mark, f"#{i}", format_size(size), filepath, file_hash
                ), tags=(tag,))

        self.tree.configure(selectmode="extended")

        # 自动选中推荐删除
        self._select_second()

        self.info_var.set(
            f"📊 共 {len(result.duplicates)} 组重复，"
            f"{result.total_duplicates} 个文件，"
            f"可释放 {format_size(result.total_wasted)}"
        )
        self.delete_btn.configure(state=NORMAL)

    # ==================== 结果操作 ====================

    def _on_search_change(self, *args):
        """搜索框变化（带防抖）"""
        if self._search_timer:
            self.root.after_cancel(self._search_timer)
        self._search_timer = self.root.after(300, self._do_search)

    def _do_search(self):
        """执行搜索过滤"""
        keyword = self.search_var.get().lower().strip()
        if not keyword:
            for item in self.tree.get_children():
                self.tree.reattach(item, "", END)
            return

        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            filepath = str(values[3]).lower()
            file_hash = str(values[4]).lower()
            if keyword in filepath or keyword in file_hash:
                self.tree.reattach(item, "", END)
            else:
                self.tree.detach(item)

    def _sort_tree(self, col: str):
        """列头排序"""
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        items = [(self.tree.set(item, col), item) for item in self.tree.get_children()]

        if col == "size":
            def parse_size(s):
                parts = s.split()
                if len(parts) == 2:
                    return float(parts[0]) * {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}.get(parts[1], 1)
                return 0
            items.sort(key=lambda x: parse_size(x[0]), reverse=self.sort_reverse)
        elif col == "group":
            items.sort(key=lambda x: int(x[0].replace("#", "")), reverse=self.sort_reverse)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=self.sort_reverse)

        for index, (val, item) in enumerate(items):
            self.tree.move(item, "", index)

        # 更新列头箭头
        for c in ["group", "size", "path"]:
            text = self.tree.heading(c, "text").replace(" ↑", "").replace(" ↓", "")
            if c == col:
                text += " ↓" if self.sort_reverse else " ↑"
            self.tree.heading(c, text=text)

    def _on_tree_click(self, event):
        """点击列表项"""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        column = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if not row or column != "#1":
            return

        filepath = self.tree.item(row, "values")[3]
        if filepath in self.selected_files:
            self.selected_files.discard(filepath)
            self.tree.set(row, "select", "☐")
        else:
            self.selected_files.add(filepath)
            self.tree.set(row, "select", "☑")

    def _on_double_click(self, event):
        """双击打开文件"""
        filepath = self._get_clicked_filepath(event)
        if filepath and os.path.exists(filepath):
            self._open_file_path(filepath)

    def _show_context_menu(self, event):
        """显示右键菜单"""
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            filepath = self._get_clicked_filepath(event)
            if filepath:
                self.context_menu.post(event.x_root, event.y_root)

    def _get_clicked_filepath(self, event) -> Optional[str]:
        """获取点击位置的文件路径"""
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        values = self.tree.item(row, "values")
        return values[3] if values else None

    def _get_selected_filepath(self) -> Optional[str]:
        """获取当前选中的文件路径"""
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        return values[3] if values else None

    def _open_file(self):
        """打开选中的文件"""
        filepath = self._get_selected_filepath()
        if filepath:
            self._open_file_path(filepath)

    def _open_folder(self):
        """打开文件所在目录"""
        filepath = self._get_selected_filepath()
        if filepath:
            self._open_folder_path(filepath)

    def _copy_path(self):
        """复制文件路径"""
        filepath = self._get_selected_filepath()
        if filepath:
            self.root.clipboard_clear()
            self.root.clipboard_append(filepath)
            self._update_status("📋 已复制路径")

    def _open_file_path(self, filepath: str):
        """用系统默认程序打开文件"""
        try:
            if os.name == 'nt':
                os.startfile(filepath)
            elif sys.platform == 'darwin':
                subprocess.run(['open', filepath], check=True)
            else:
                subprocess.run(['xdg-open', filepath], check=True)
            self._update_status(f"📄 已打开文件")
        except Exception as e:
            logger.error(f"打开文件失败: {filepath} - {e}")
            messagebox.showerror("错误", f"无法打开文件:\n{type(e).__name__}")

    def _open_folder_path(self, filepath: str):
        """打开文件所在目录"""
        try:
            if os.name == 'nt':
                subprocess.run(['explorer', '/select,', filepath], check=True)
            elif sys.platform == 'darwin':
                subprocess.run(['open', '-R', filepath], check=True)
            else:
                subprocess.run(['xdg-open', str(Path(filepath).parent)], check=True)
            self._update_status(f"📁 已打开目录")
        except Exception as e:
            logger.error(f"打开目录失败: {filepath} - {e}")
            messagebox.showerror("错误", f"无法打开目录:\n{type(e).__name__}")

    def _select_second(self):
        """全选每组重复文件（保留第一个）"""
        self.selected_files.clear()
        if self.scan_result:
            for _, files, _ in self.scan_result.duplicates:
                for filepath in files[1:]:
                    self.selected_files.add(filepath)
        self._refresh_checkmarks()

    def _invert_selection(self):
        """反选"""
        all_files = set()
        if self.scan_result:
            for _, files, _ in self.scan_result.duplicates:
                all_files.update(files[1:])
        self.selected_files = all_files - self.selected_files
        self._refresh_checkmarks()

    def _clear_selection(self):
        """取消全选"""
        self.selected_files.clear()
        self._refresh_checkmarks()

    def _refresh_checkmarks(self):
        """刷新勾选状态"""
        original_files = set()
        if self.scan_result:
            for _, files, _ in self.scan_result.duplicates:
                original_files.add(files[0])

        for item in self.tree.get_children():
            filepath = self.tree.item(item, "values")[3]
            if filepath in self.selected_files:
                self.tree.set(item, "select", "☑")
            else:
                self.tree.set(item, "select", "⬜" if filepath in original_files else "☐")

    # ==================== 删除操作 ====================

    def _delete_selected(self):
        """删除选中的文件"""
        if not self.selected_files:
            messagebox.showinfo("提示", "请先选择要删除的文件")
            return

        # 检查每组是否至少保留一个
        if self.scan_result:
            for i, (_, files, _) in enumerate(self.scan_result.duplicates, 1):
                remaining = [f for f in files if f not in self.selected_files]
                if not remaining:
                    messagebox.showwarning("⚠️ 警告", f"第 #{i} 组的所有文件都被选中删除\n请至少保留一个文件")
                    return

        files_list = sorted(self.selected_files)
        count = len(files_list)

        # 计算总大小
        total_size = 0
        for f in files_list:
            try:
                total_size += os.path.getsize(f)
            except OSError:
                pass

        # 选择删除方式
        use_trash = False
        if is_send2trash_available():
            use_trash = messagebox.askyesno(
                "删除方式",
                f"确定要删除 {count} 个文件吗？\n\n"
                f"💾 释放空间: {format_size(total_size)}\n\n"
                f"「是」移到回收站（可恢复）\n「否」永久删除（不可恢复）"
            )
        else:
            if not messagebox.askyesno(
                "确认删除",
                f"确定要永久删除 {count} 个文件吗？\n\n"
                f"💾 释放空间: {format_size(total_size)}\n\n"
                f"⚠️ 此操作不可撤销！\n"
                f"（提示：安装 send2trash 可支持移到回收站）"
            ):
                return

        # 执行删除
        success, failed, errors = self._do_delete(files_list, use_trash)

        action = "移到回收站" if use_trash else "永久删除"
        result_msg = f"✅ {action}完成\n\n成功: {success} 个\n失败: {failed} 个"
        if errors:
            result_msg += "\n\n❌ 失败:\n" + "\n".join(errors[:5])

        messagebox.showinfo("完成", result_msg)

        if success > 0:
            self._start_scan()

    def _do_delete(self, files: list, use_trash: bool) -> tuple:
        """
        执行文件删除

        Returns:
            (success_count, fail_count, error_messages)
        """
        success = 0
        failed = 0
        errors = []

        for filepath in files:
            try:
                if use_trash:
                    import send2trash
                    send2trash.send2trash(filepath)
                else:
                    os.remove(filepath)
                success += 1
            except Exception as e:
                failed += 1
                errors.append(f"{Path(filepath).name}: {e}")
                logger.error(f"删除文件失败: {filepath} - {e}")

        return success, failed, errors

    # ==================== 导出操作 ====================

    def _export_results(self):
        """导出扫描结果为 CSV"""
        if not self.scan_result or not self.scan_result.duplicates:
            messagebox.showinfo("提示", "没有可导出的扫描结果，请先扫描")
            return

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

                for i, (file_hash, files, size) in enumerate(self.scan_result.duplicates, 1):
                    for file_path in files:
                        selected = "是" if file_path in self.selected_files else "否"
                        writer.writerow([f"#{i}", format_size(size), file_hash, file_path, selected])

            messagebox.showinfo("成功", f"扫描结果已导出到:\n{filepath}")
        except Exception as e:
            logger.error(f"导出失败: {e}")
            messagebox.showerror("错误", f"导出失败: {e}")

    # ==================== 帮助 ====================

    def _show_help(self):
        """显示使用说明"""
        help_text = f"""📖 使用说明 (v{__version__})

1. 选择目录
   点击「浏览」或从下拉列表选择最近目录

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
   点击「🗑️ 删除选中」确认"""

        win = tk.Toplevel(self.root)
        win.title("使用说明")
        win.geometry("500x500")
        win.transient(self.root)

        text = tk.Text(win, wrap=tk.WORD, padx=15, pady=15, font=("Microsoft YaHei UI", 10))
        text.pack(fill=tk.BOTH, expand=True)
        text.insert(tk.END, help_text)
        text.configure(state=tk.DISABLED)

    def _show_shortcuts(self):
        """显示快捷键"""
        messagebox.showinfo("快捷键", """⌨️ 快捷键

Ctrl+O    选择目录
Ctrl+S    开始扫描
Ctrl+E    导出结果
Ctrl+Q    退出程序
F1        显示帮助
F5        刷新扫描""")

    def _show_about(self):
        """显示关于信息"""
        messagebox.showinfo("关于", f"""🔍 Duplicate Cleaner
重复文件清理工具

版本：v{__version__}
作者：Kanji

功能特点：
• 基于文件内容哈希精准识别重复
• 多线程并行扫描，速度快
• 支持图形界面，操作简单
• 安全删除机制，防止误删

技术栈：
• Python 3.8+
• tkinter + ttkbootstrap
• hashlib / threading""")

    # ==================== 工具方法 ====================

    def _update_status(self, text: str):
        """更新状态文本（线程安全）"""
        self.root.after(0, lambda: self.status_var.set(text))

    def _update_progress(self, value: float):
        """更新进度条（线程安全）"""
        self.root.after(0, lambda: self.progress_var.set(value))


def main():
    """GUI 主入口"""
    _init_ttk()

    if _has_bootstrap:
        root = _ttk.Window(
            title=f"Duplicate Cleaner v{__version__}",
            themename="litera",
            size=(1300, 800),
            minsize=(1000, 600)
        )
    else:
        root = tk.Tk()

    app = DuplicateCleanerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
