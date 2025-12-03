#!/usr/bin/env python3
"""
简易前端 UI（Tkinter）：为微信聊天 OCR 扫描提供最小化的人机交互界面。

功能与场景：
- 允许用户手动设置窗口标题、聊天区域坐标、滚动方向与限速、OCR 语言、导出格式与输出目录；
- 提供“预览聊天区域”功能，便于校准 --chat-area 的坐标；
- 一键执行 auto_wechat_scan.py 并在界面中显示运行日志；

设计选择：
- 使用 Tkinter（Python 标准库）以减少依赖；
- 通过子进程运行 CLI，避免与现有控制器强耦合，提升稳定性；
- 在 macOS 上通过 'open' 命令打开输出目录；

注意：
- 需授予屏幕录制与辅助功能权限；
- OCR 模型首次加载较慢属正常现象；
"""

import os
import sys
import threading
import subprocess
import json
import shlex
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List

from PIL import Image, ImageTk, ImageGrab


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 默认 Python 解释器：优先使用当前进程的解释器，其次回退到通用命令名
# 说明：避免硬编码个人路径以提升跨平台可移植性
PYTHON_BIN = sys.executable or "python3"


class SimpleWechatGUI:
    """简易微信 OCR 扫描 GUI

    函数级注释：
    - 负责构建 Tkinter 界面、收集输入参数、拼接命令并以子进程运行 CLI；
    - 提供预览聊天区域（调用 scripts/capture_rect_preview.py）以辅助坐标校准；
    - 在日志文本区实时显示子进程输出（stdout/stderr）。
    """

    def __init__(self, root: tk.Tk):
        """初始化 GUI 组件与默认值"""
        self.root = root
        self.root.title("WeChat OCR 简易前端")
        self.preview_image = None
        self.paused = False
        self.log_file = None
        self.current_log_path = ""
        self.pause_timer_id = None
        self.var_status = tk.StringVar(value="空闲")
        self.var_current_log = tk.StringVar(value="")

        # 字段变量
        # Python 解释器路径（默认自动检测当前进程解释器，可在 UI 中修改或再次自动检测）
        self.var_python_bin = tk.StringVar(value=(sys.executable or PYTHON_BIN))
        self.var_window_title = tk.StringVar()
        self.var_chat_area = tk.StringVar()
        self.var_direction = tk.StringVar(value="up")
        self.var_full_fetch = tk.BooleanVar(value=False)
        self.var_go_top_first = tk.BooleanVar(value=False)
        self.var_skip_empty = tk.BooleanVar(value=True)
        self.var_verbose = tk.BooleanVar(value=True)
        self.var_ocr_lang = tk.StringVar(value="ch")
        self.var_output_dir = tk.StringVar(value=os.path.join(PROJECT_ROOT, "output"))
        self.var_filename_prefix = tk.StringVar(value="auto_wechat_scan")
        self.var_scroll_delay = tk.StringVar(value="")
        self.var_max_scrolls = tk.StringVar(value="60")
        self.var_max_spm = tk.StringVar(value="40")
        self.var_spm_range = tk.StringVar(value="")

        self.format_vars = {
            "json": tk.BooleanVar(value=True),
            "csv": tk.BooleanVar(value=True),
            "md": tk.BooleanVar(value=False),
            "txt": tk.BooleanVar(value=False),
        }

        self._build_layout()
        
        # 绑定窗口尺寸变化事件以实现响应式调整
        try:
            self.root.bind("<Configure>", self._on_window_resize)
            self._apply_responsive_layout()
        except Exception:
            pass
        try:
            self._apply_responsive_layout()
        except Exception:
            pass

    def _build_layout(self):
        """构建界面布局与控件"""
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        try:
            for i in range(0, 10):
                frm.columnconfigure(i, weight=1)
        except Exception:
            pass

        # 顶部状态与当前日志文件名
        row = 0
        ttk.Label(frm, text="状态:").grid(row=row, column=0, sticky=tk.W)
        ttk.Label(frm, textvariable=self.var_status).grid(row=row, column=1, sticky=tk.W)
        ttk.Label(frm, text="当前扫描日志:").grid(row=row, column=2, sticky=tk.W)
        ttk.Label(frm, textvariable=self.var_current_log).grid(row=row, column=3, columnspan=3, sticky=tk.W)

        # 第一行：Python 解释器路径
        row += 1
        ttk.Label(frm, text="Python 解释器路径:").grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_python_bin, width=34).grid(row=row, column=1, columnspan=3, sticky=tk.EW, padx=6, pady=3)
        ttk.Button(frm, text="自动检测", command=self.on_detect_python, width=10).grid(row=row, column=4, sticky=tk.EW, padx=6, pady=3)

        # 第二行：窗口标题、聊天区域
        row += 1
        ttk.Label(frm, text="窗口标题（可选）:").grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_window_title, width=24).grid(row=row, column=1, sticky=tk.EW, padx=6, pady=3)
        ttk.Label(frm, text="聊天区域坐标 x,y,w,h（可选）:").grid(row=row, column=2, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_chat_area, width=16).grid(row=row, column=3, sticky=tk.EW, padx=6, pady=3)
        ttk.Button(frm, text="预览聊天区域", command=self.on_preview_chat_area, width=12).grid(row=row, column=4, sticky=tk.EW, padx=6, pady=3)
        ttk.Button(frm, text="框选聊天区域", command=self.on_select_chat_area, width=12).grid(row=row, column=5, sticky=tk.EW, padx=6, pady=3)

        # 第三行：滚动与 OCR
        row += 1
        ttk.Label(frm, text="方向:").grid(row=row, column=0, sticky=tk.W)
        ttk.Combobox(frm, textvariable=self.var_direction, values=["up", "down"], width=6, state="readonly").grid(row=row, column=1, sticky=tk.EW)
        ttk.Label(frm, text="scroll-delay（秒，可空）:").grid(row=row, column=2, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_scroll_delay, width=6).grid(row=row, column=3, sticky=tk.EW, padx=6, pady=3)
        ttk.Label(frm, text="OCR 语言:").grid(row=row, column=4, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_ocr_lang, width=5).grid(row=row, column=5, sticky=tk.EW, padx=6, pady=3)

        # 第四行：阈值与开关
        row += 1
        ttk.Label(frm, text="max-scrolls:").grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_max_scrolls, width=6).grid(row=row, column=1, sticky=tk.EW)
        ttk.Label(frm, text="每分钟滚动 (spm):").grid(row=row, column=2, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_max_spm, width=6).grid(row=row, column=3, sticky=tk.EW)
        ttk.Label(frm, text="spm范围(min,max，可选):").grid(row=row, column=4, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_spm_range, width=12).grid(row=row, column=5, sticky=tk.EW)
        ttk.Checkbutton(frm, text="full-fetch", variable=self.var_full_fetch).grid(row=row, column=6, sticky=tk.W)
        ttk.Checkbutton(frm, text="go-top-first", variable=self.var_go_top_first).grid(row=row, column=7, sticky=tk.W)

        # 第五行：导出与目录
        row += 1
        ttk.Label(frm, text="导出格式:").grid(row=row, column=0, sticky=tk.W)
        col = 1
        for name in ["json", "csv", "md", "txt"]:
            ttk.Checkbutton(frm, text=name, variable=self.format_vars[name]).grid(row=row, column=col, sticky=tk.EW)
            col += 1
        ttk.Label(frm, text="输出目录:").grid(row=row, column=4, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_output_dir, width=22).grid(row=row, column=5, sticky=tk.EW, padx=6, pady=3)
        ttk.Button(frm, text="选择…", command=self.on_choose_output, width=8).grid(row=row, column=6, sticky=tk.EW, padx=6, pady=3)

        # 第六行：文件名前缀与开关
        row += 1
        ttk.Label(frm, text="文件前缀:").grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_filename_prefix, width=16).grid(row=row, column=1, sticky=tk.EW, padx=6, pady=3)
        ttk.Checkbutton(frm, text="skip-empty", variable=self.var_skip_empty).grid(row=row, column=2, sticky=tk.EW)
        ttk.Checkbutton(frm, text="verbose", variable=self.var_verbose).grid(row=row, column=3, sticky=tk.EW)
        ttk.Button(frm, text="打开输出目录", command=self.on_open_output).grid(row=row, column=4, sticky=tk.EW)

        # 第七行：操作按钮
        row += 1
        self.btn_start = ttk.Button(frm, text="开始扫描", command=self.on_start_scan, width=12)
        self.btn_start.grid(row=row, column=0, sticky=tk.EW, padx=6, pady=4)
        self.btn_stop = ttk.Button(frm, text="停止扫描", command=self.on_stop_scan, state="disabled", width=12)
        self.btn_stop.grid(row=row, column=1, sticky=tk.EW, padx=6, pady=4)
        self.btn_pause = ttk.Button(frm, text="暂停扫描", command=self.on_pause_resume, state="disabled", width=12)
        self.btn_pause.grid(row=row, column=2, sticky=tk.EW, padx=6, pady=4)
        ttk.Button(frm, text="复制命令", command=self.on_copy_command, width=12).grid(row=row, column=3, sticky=tk.EW, padx=6, pady=4)
        ttk.Button(frm, text="保存配置", command=self.on_save_config, width=12).grid(row=row, column=4, sticky=tk.EW, padx=6, pady=4)
        ttk.Button(frm, text="加载配置", command=self.on_load_config, width=12).grid(row=row, column=5, sticky=tk.EW, padx=6, pady=4)
        ttk.Button(frm, text="从配置服务加载", command=self.on_load_from_server, width=14).grid(row=row, column=6, sticky=tk.EW, padx=6, pady=4)
        ttk.Button(frm, text="退出", command=self.root.quit, width=8).grid(row=row, column=7, sticky=tk.EW, padx=6, pady=4)
        ttk.Button(frm, text="查看最新导出", command=self.on_show_latest_exports, width=14).grid(row=row, column=8, sticky=tk.EW, padx=6, pady=4)
        ttk.Button(frm, text="最新导出列表", command=self.on_open_latest_exports_window, width=14).grid(row=row, column=9, sticky=tk.EW, padx=6, pady=4)

        # 预览图与日志
        row += 1
        self.preview_label = ttk.Label(frm, text="预览图将在此显示")
        self.preview_label.grid(row=row, column=0, columnspan=3, sticky=tk.EW)
        self.log_text = tk.Text(frm, height=20, width=120)
        self.log_text.grid(row=row, column=3, columnspan=7, sticky=tk.NSEW)
        try:
            frm.rowconfigure(row, weight=1)
        except Exception:
            pass

        # 第八行：消息样式预览（引用气泡“我/对方”标签）
        row += 1
        ttk.Label(frm, text="消息样式预览（引用气泡标签）:").grid(row=row, column=0, sticky=tk.W)
        self.style_canvas = tk.Canvas(frm, width=540, height=160, bg="#ffffff", highlightthickness=1, highlightbackground="#e5eaf0")
        self.style_canvas.grid(row=row, column=1, columnspan=6, sticky=tk.W, padx=(6,0))
        try:
            self._render_message_style_preview()
        except Exception:
            # 容错：若渲染失败不影响主流程
            pass

    def _get_formats(self) -> str:
        """收集导出格式复选框，拼接为逗号分隔字符串"""
        chosen: List[str] = [name for name, var in self.format_vars.items() if var.get()]
        return ",".join(chosen) if chosen else "json"

    def _build_scan_command(self) -> List[str]:
        """根据界面参数构建 auto_wechat_scan.py 的命令行列表

        函数级注释：
        - 优先使用界面中的 Python 解释器路径（var_python_bin）；
        - 当未设置或为空时回退到默认常量 PYTHON_BIN；
        - 其余参数保持原有逻辑按需追加。
        """
        python_bin = (self.var_python_bin.get().strip() or PYTHON_BIN)
        cmd = [python_bin, os.path.join(PROJECT_ROOT, "cli", "auto_wechat_scan.py")]
        cmd += ["--direction", self.var_direction.get()]
        cmd += ["--max-scrolls", self.var_max_scrolls.get()]
        cmd += ["--max-scrolls-per-minute", self.var_max_spm.get()]
        if self.var_full_fetch.get():
            cmd.append("--full-fetch")
        if self.var_go_top_first.get():
            cmd.append("--go-top-first")
        if self.var_window_title.get().strip():
            cmd += ["--window-title", self.var_window_title.get().strip()]
        if self.var_chat_area.get().strip():
            cmd += ["--chat-area", self.var_chat_area.get().strip()]
        if self.var_ocr_lang.get().strip():
            cmd += ["--ocr-lang", self.var_ocr_lang.get().strip()]
        formats = self._get_formats()
        if formats:
            cmd += ["--formats", formats]
        outdir = self.var_output_dir.get().strip() or os.path.join(PROJECT_ROOT, "output")
        cmd += ["--output", outdir]
        cmd += ["--filename-prefix", self.var_filename_prefix.get().strip()]
        if self.var_skip_empty.get():
            cmd.append("--skip-empty")
        if self.var_verbose.get():
            cmd.append("--verbose")
        if self.var_scroll_delay.get().strip():
            cmd += ["--scroll-delay", self.var_scroll_delay.get().strip()]
        if self.var_spm_range.get().strip():
            cmd += ["--spm-range", self.var_spm_range.get().strip()]
        return cmd

    def _append_log(self, text: str):
        """将文本追加到日志区域并滚动到底部（线程安全）

        函数级注释：
        - Tkinter 非线程安全，后台线程不应直接操作控件；
        - 若当前线程非主线程，则通过 root.after 调度到主线程执行；
        - 统一在末尾调用 see(tk.END) 保证滚动到最新。
        """
        try:
            if threading.current_thread() is threading.main_thread():
                self.log_text.insert(tk.END, text + "\n")
                self.log_text.see(tk.END)
            else:
                self.root.after(0, lambda: self._append_log(text))
        except Exception:
            # 最后容错：避免日志写入异常导致崩溃
            pass

    def _quote_cmd(self, cmd: List[str]) -> str:
        """将命令数组安全地转换为可在 Shell 中执行的字符串

        函数级注释：
        - 使用 shlex.quote 为每个参数添加必要的转义，避免路径或参数中空格/特殊字符造成问题；
        - 返回的字符串可直接在 zsh/bash 下粘贴执行。
        """
        try:
            return " ".join(shlex.quote(part) for part in cmd)
        except Exception:
            # 如果异常，退回到简单拼接
            return " ".join(cmd)

    def _validate_python_bin(self) -> bool:
        """校验当前设置的 Python 解释器路径是否可用

        函数级注释：
        - 检查路径是否存在且为可执行文件；
        - 若不可用则弹窗提示，并在日志中记录原因；
        - 返回布尔值供调用方决定是否继续。
        """
        python_bin = (self.var_python_bin.get().strip() or PYTHON_BIN)
        if not python_bin:
            self._append_log("Python 路径为空，请先填写或点击‘自动检测’")
            try:
                messagebox.showwarning("提示", "Python 路径为空，请先填写或点击‘自动检测’")
            except Exception:
                pass
            return False
        if not os.path.exists(python_bin):
            self._append_log(f"Python 路径不存在: {python_bin}")
            try:
                messagebox.showerror("错误", f"Python 路径不存在: {python_bin}")
            except Exception:
                pass
            return False
        if not os.access(python_bin, os.X_OK):
            self._append_log(f"Python 路径不可执行: {python_bin}")
            try:
                messagebox.showerror("错误", f"Python 路径不可执行: {python_bin}")
            except Exception:
                pass
            return False
        return True

    def _ensure_output_dir(self) -> str:
        """确保输出目录存在且可写，必要时自动创建

        函数级注释：
        - 若变量为空则回退到默认目录 PROJECT_ROOT/output；
        - 若目录不存在自动创建；
        - 简单检查写权限（创建并删除一个临时文件）。
        """
        outdir = self.var_output_dir.get().strip() or os.path.join(PROJECT_ROOT, "output")
        try:
            os.makedirs(outdir, exist_ok=True)
            test_file = os.path.join(outdir, ".ui_write_test.tmp")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_file)
        except Exception as e:
            self._append_log(f"输出目录不可写: {outdir}, {e}")
            try:
                messagebox.showerror("错误", f"输出目录不可写: {outdir}\n{e}")
            except Exception:
                pass
            raise
        return outdir

    def _update_preview_from_chat_area(self):
        """根据当前聊天区域坐标抓取一次预览图并显示在左侧预览区"""
        rect = self.var_chat_area.get().strip()
        if not rect:
            return
        try:
            parts = [p.strip() for p in rect.split(",")]
            if len(parts) != 4:
                return
            x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            if w <= 0 or h <= 0:
                return
            bbox = (x, y, x + w, y + h)
            img = ImageGrab.grab(bbox=bbox)
            img.thumbnail((400, 400))
            self.preview_image = ImageTk.PhotoImage(img)
            self.preview_label.configure(image=self.preview_image)
            self.preview_label.image = self.preview_image
        except Exception:
            pass

    def on_start_scan(self):
        """启动扫描：在后台线程中执行命令并实时输出日志；每次开始创建新的扫描日志文件"""
        # 1) 预检查 Python 路径与输出目录
        if not self._validate_python_bin():
            return
        try:
            outdir = self._ensure_output_dir()
            self._append_log(f"输出目录: {outdir}")
        except Exception:
            return
        # 创建新的扫描日志文件
        try:
            path = self._create_new_log_file()
            if path:
                self._append_log(f"当前扫描日志: {path}")
        except Exception:
            pass
        # 2) 构建命令
        cmd = self._build_scan_command()
        self._append_log("运行命令: " + " ".join(cmd))
        self.last_cmd = cmd
        # 在开始扫描前，若设置了聊天区域坐标，则抓取一次预览图显示
        try:
            self._update_preview_from_chat_area()
        except Exception:
            pass
        # 切换按钮状态：开始 -> 禁用，停止 -> 启用
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_pause.configure(state="normal")
        self.var_status.set("扫描中")

        def worker():
            try:
                self.scan_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in self.scan_proc.stdout:
                    line = line.rstrip()
                    self._append_log(line)
                    self._write_log_line_to_file(line)
                code = self.scan_proc.wait()
                self._append_log(f"进程退出码: {code}")
                if code == 0:
                    try:
                        messagebox.showinfo("完成", "扫描完成")
                    except Exception:
                        pass
                else:
                    try:
                        messagebox.showwarning("警告", f"扫描退出码: {code}")
                    except Exception:
                        pass
            except Exception as e:
                self._append_log(f"执行失败: {e}")
                try:
                    messagebox.showerror("错误", str(e))
                except Exception:
                    pass
            finally:
                # 回到可点击状态
                def restore_buttons():
                    if not getattr(self, "paused", False):
                        self.var_status.set("空闲")
                        self.btn_start.configure(state="normal")
                        self.btn_stop.configure(state="disabled")
                        self.btn_pause.configure(state="disabled", text="暂停扫描")
                        try:
                            if self.log_file:
                                self.log_file.close()
                                self.log_file = None
                                self.var_current_log.set("")
                        except Exception:
                            pass
                    else:
                        self.btn_stop.configure(state="normal")
                        self.btn_pause.configure(state="normal", text="继续扫描")
                try:
                    self.root.after(0, restore_buttons)
                except Exception:
                    pass

        self.scan_thread = threading.Thread(target=worker, daemon=True)
        self.scan_thread.start()

    def on_preview_chat_area(self):
        """生成聊天区域预览图：内置截图逻辑直接截取屏幕区域并显示（不依赖外部脚本）

        函数级注释：
        - 解析 x,y,w,h 后使用 Pillow 的 ImageGrab.grab(bbox=...) 截取指定区域；
        - 将图片保存到项目 outputs/debug_chat_area_preview.png 并在左侧预览；
        - 相比调用脚本，内置实现减少依赖（无需安装 pyautogui）。
        """
        rect = self.var_chat_area.get().strip()
        if not rect:
            messagebox.showinfo("提示", "请先输入聊天区域坐标，例如 120,80,920,900")
            return
        out_png = os.path.join(PROJECT_ROOT, "outputs", "debug_chat_area_preview.png")
        try:
            parts = [p.strip() for p in rect.split(",")]
            if len(parts) != 4:
                messagebox.showerror("错误", "聊天区域坐标格式应为 x,y,w,h")
                return
            x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            if w <= 0 or h <= 0:
                messagebox.showerror("错误", "宽或高必须为正数")
                return
            bbox = (x, y, x + w, y + h)
            img = ImageGrab.grab(bbox=bbox)
            os.makedirs(os.path.dirname(out_png), exist_ok=True)
            img.save(out_png)
            img.thumbnail((400, 400))
            self.preview_image = ImageTk.PhotoImage(img)
            self.preview_label.configure(image=self.preview_image)
            self.preview_label.image = self.preview_image
            self._append_log(f"预览已保存: {out_png}")
        except Exception as e:
            messagebox.showerror("错误", f"预览失败: {e}")

    def on_select_chat_area(self):
        """通过屏幕截图 + Canvas 框选的方式，生成聊天区域坐标并回填到输入框

        函数级注释：
        - 使用 Pillow 的 ImageGrab 抓取屏幕快照；
        - 在 Toplevel 窗口的 Canvas 上绑定鼠标事件以绘制选区；
        - 根据显示缩放比换算为真实屏幕坐标，更新 var_chat_area。
        """
        try:
            screenshot = ImageGrab.grab()
        except Exception as e:
            messagebox.showerror("错误", f"无法抓取屏幕截图，请检查屏幕录制权限：{e}")
            return

        # 计算显示缩放，控制在合理窗口尺寸
        max_w, max_h = 1200, 800
        sw, sh = screenshot.width, screenshot.height
        scale = min(max_w / sw, max_h / sh)
        if scale > 1:
            scale = 1.0
        disp_w, disp_h = int(sw * scale), int(sh * scale)
        display_img = screenshot.resize((disp_w, disp_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(display_img)

        top = tk.Toplevel(self.root)
        top.title("框选聊天区域（按拖拽左键选区，松开结束）")
        top.geometry(f"{disp_w}x{disp_h}")
        canvas = tk.Canvas(top, width=disp_w, height=disp_h, cursor="cross")
        canvas.pack()
        canvas.create_image(0, 0, image=photo, anchor=tk.NW)
        # 防止图片被 GC 回收
        canvas.image = photo

        rect_id = {"id": None}
        state = {"x0": 0, "y0": 0}

        def on_press(event):
            """鼠标按下事件：记录起点并创建矩形框"""
            state["x0"], state["y0"] = event.x, event.y
            if rect_id["id"]:
                canvas.delete(rect_id["id"])
            rect_id["id"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)

        def on_move(event):
            """拖动事件：更新选区矩形的右下角坐标"""
            if rect_id["id"]:
                canvas.coords(rect_id["id"], state["x0"], state["y0"], event.x, event.y)

        def on_release(event):
            """释放事件：计算真实屏幕坐标并写入 var_chat_area"""
            x1, y1 = event.x, event.y
            x0, y0 = state["x0"], state["y0"]
            x_min, y_min = min(x0, x1), min(y0, y1)
            w = abs(x1 - x0)
            h = abs(y1 - y0)
            if w < 3 or h < 3:
                messagebox.showinfo("提示", "选区过小，请重新框选")
                return
            real_x = int(x_min / scale)
            real_y = int(y_min / scale)
            real_w = int(w / scale)
            real_h = int(h / scale)
            self.var_chat_area.set(f"{real_x},{real_y},{real_w},{real_h}")
            self._append_log(f"框选坐标: {self.var_chat_area.get()}")
            top.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_release)
        # 允许按 Esc 取消并关闭窗口
        top.bind("<Escape>", lambda _: top.destroy())

    def _render_message_style_preview(self):
        """在 Canvas 中绘制两条示例引用气泡，分别标注“对方”与“我”。

        函数级注释：
        - 使用 Tkinter Canvas 基本图形绘制简化的聊天气泡；
        - 左侧灰色气泡表示“对方”，右侧蓝色气泡表示“我”；
        - 左上角以灰色小字标注身份标签，正文仅展示纯文本内容（示例）。
        """
        c = getattr(self, "style_canvas", None)
        if not c:
            return
        c.delete("all")
        # 对方气泡
        x, y, w, h = 10, 10, 240, 110
        c.create_rectangle(x, y, x + w, y + h, fill="#f5f5f5", outline="#d9d9d9")
        c.create_text(x + 10, y + 12, text="对方", anchor=tk.W, fill="#888888", font=("Arial", 10))
        c.create_text(x + 12, y + 36, text="“明天见”", anchor=tk.W, fill="#1f2328", font=("Arial", 12))
        # 我方气泡
        x2, y2, w2, h2 = 280, 10, 240, 110
        c.create_rectangle(x2, y2, x2 + w2, y2 + h2, fill="#e6f4ff", outline="#91caff")
        c.create_text(x2 + 10, y2 + 12, text="我", anchor=tk.W, fill="#888888", font=("Arial", 10))
        c.create_text(x2 + 12, y2 + 36, text="“请查看这段”", anchor=tk.W, fill="#1f2328", font=("Arial", 12))

    def _apply_responsive_layout(self):
        """根据屏幕尺寸应用响应式布局（窗口宽度不超过屏幕宽度的60%）"""
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = int(sw * 0.6)
            h = int(min(0.8 * sh, 820))
            self.root.geometry(f"{w}x{h}")
            base_font = 12 if sw >= 1800 else (11 if sw >= 1440 else 10)
            self.root.option_add("*Font", ("Arial", base_font))
        except Exception:
            pass

    def _on_window_resize(self, event):
        """窗口尺寸变化事件：动态调整字体与日志区扩展以适配超宽屏"""
        try:
            sw = self.root.winfo_screenwidth()
            w = max(400, int(event.width))
            base_font = 12 if sw >= 1800 else (11 if sw >= 1440 else 10)
            adj = base_font if w >= int(sw * 0.5) else (base_font - 1 if w >= int(sw * 0.4) else base_font - 2)
            self.root.option_add("*Font", ("Arial", max(9, adj)))
        except Exception:
            pass

    def _apply_responsive_layout(self):
        """根据屏幕尺寸应用响应式布局（窗口宽度不超过屏幕宽度的60%）"""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = int(sw * 0.6)
        h = int(min(0.8 * sh, 820))
        try:
            self.root.geometry(f"{w}x{h}")
        except Exception:
            pass
        base_font = 12 if sw >= 1440 else (11 if sw >= 1280 else 10)
        try:
            self.root.option_add("*Font", ("Arial", base_font))
        except Exception:
            pass

    def _create_new_log_file(self) -> str:
        """创建新的扫描日志文件（scan_YYYYMMDD_HHMMSS.log）"""
        import datetime
        outdir = self._ensure_output_dir()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(outdir, f"scan_{ts}.log")
        try:
            if self.log_file:
                try:
                    self.log_file.close()
                except Exception:
                    pass
            self.log_file = open(path, "a", encoding="utf-8")
            self.current_log_path = path
            self.var_current_log.set(path)
            return path
        except Exception:
            self.current_log_path = ""
            return ""

    def _write_log_line_to_file(self, line: str):
        """将子进程输出追加写入当前日志文件"""
        try:
            if self.log_file:
                self.log_file.write(line + "\n")
                self.log_file.flush()
        except Exception:
            pass

    def on_pause_resume(self):
        """暂停或继续扫描：终止子进程但保持日志文件；继续时复用日志文件"""
        # 扫描中 -> 暂停
        if hasattr(self, "scan_proc") and self.scan_proc and self.scan_proc.poll() is None:
            try:
                self.scan_proc.terminate()
            except Exception:
                pass
            self.paused = True
            self.var_status.set("已暂停")
            self.btn_pause.configure(text="继续扫描")
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            try:
                if self.pause_timer_id:
                    self.root.after_cancel(self.pause_timer_id)
                self.pause_timer_id = self.root.after(30*60*1000, self._auto_stop_from_pause)
            except Exception:
                pass
            return
        # 已暂停 -> 继续
        if self.paused:
            cmd = getattr(self, "last_cmd", None) or self._build_scan_command()
            self.var_status.set("扫描中")
            self.btn_pause.configure(text="暂停扫描")
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            def worker():
                try:
                    self.scan_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in self.scan_proc.stdout:
                        line = line.rstrip()
                        self._append_log(line)
                        self._write_log_line_to_file(line)
                    code = self.scan_proc.wait()
                    self._append_log(f"进程退出码: {code}")
                except Exception as e:
                    self._append_log(f"执行失败: {e}")
                finally:
                    def restore():
                        if not self.paused:
                            self.btn_start.configure(state="normal")
                            self.btn_stop.configure(state="disabled")
                            self.btn_pause.configure(state="disabled", text="暂停扫描")
                            self.var_status.set("空闲")
                            try:
                                if self.log_file:
                                    self.log_file.close()
                                    self.log_file = None
                                    self.var_current_log.set("")
                            except Exception:
                                pass
                        else:
                            self.btn_stop.configure(state="normal")
                            self.btn_pause.configure(state="normal")
                    try:
                        self.root.after(0, restore)
                    except Exception:
                        pass
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            self.paused = False
            try:
                if self.pause_timer_id:
                    self.root.after_cancel(self.pause_timer_id)
                    self.pause_timer_id = None
            except Exception:
                pass

    def _auto_stop_from_pause(self):
        """暂停超过30分钟后自动停止并重置界面"""
        self.paused = False
        self.var_status.set("空闲")
        try:
            if hasattr(self, "scan_proc") and self.scan_proc and self.scan_proc.poll() is None:
                self.scan_proc.terminate()
        except Exception:
            pass
        try:
            if self.log_file:
                self.log_file.close()
                self.log_file = None
                self.var_current_log.set("")
        except Exception:
            pass
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_pause.configure(state="disabled", text="暂停扫描")

    def on_choose_output(self):
        """选择输出目录（使用原生文件夹选择对话框）"""
        dirname = filedialog.askdirectory(initialdir=self.var_output_dir.get())
        if dirname:
            self.var_output_dir.set(dirname)

    def on_open_output(self):
        """在 macOS 上打开输出目录"""
        outdir = self.var_output_dir.get().strip()
        if not outdir:
            messagebox.showinfo("提示", "请先设置输出目录")
            return
        try:
            subprocess.run(["open", outdir], check=True)
        except Exception as e:
            messagebox.showerror("错误", f"打开目录失败: {e}")

    def on_stop_scan(self):
        """停止扫描子进程并恢复按钮状态；关闭当前扫描日志文件"""
        if hasattr(self, "scan_proc") and self.scan_proc and self.scan_proc.poll() is None:
            try:
                self.scan_proc.terminate()
                self._append_log("已请求终止扫描进程…")
                try:
                    code = self.scan_proc.wait(timeout=5)
                    self._append_log(f"扫描进程已结束，退出码: {code}")
                except subprocess.TimeoutExpired:
                    self._append_log("终止超时，将强制结束进程…")
                    try:
                        self.scan_proc.kill()
                        code = self.scan_proc.wait(timeout=3)
                        self._append_log(f"已强制结束，退出码: {code}")
                    except Exception as e:
                        self._append_log(f"强制结束失败: {e}")
            except Exception as e:
                self._append_log(f"终止失败: {e}")
        else:
            self._append_log("当前无正在运行的扫描进程。")
        # 恢复按钮状态
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_pause.configure(state="disabled", text="暂停扫描")
        self.var_status.set("空闲")
        self.paused = False
        try:
            if self.log_file:
                self.log_file.close()
                self.log_file = None
                self.var_current_log.set("")
        except Exception:
            pass
        try:
            if self.pause_timer_id:
                self.root.after_cancel(self.pause_timer_id)
                self.pause_timer_id = None
        except Exception:
            pass

    def on_copy_command(self):
        """构建命令并复制到剪贴板

        函数级注释：
        - 使用 _build_scan_command() 拼接命令字符串；
        - 调用 Tk 的剪贴板 API 将命令复制，以便用户在终端直接执行。
        """
        # 预检查 Python 路径，避免复制不可用的命令
        if not self._validate_python_bin():
            return
        cmd = self._build_scan_command()
        cmd_str = self._quote_cmd(cmd)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd_str)
            messagebox.showinfo("已复制", "命令已复制到剪贴板")
            self._append_log("已复制命令: " + cmd_str)
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")

    def on_show_latest_exports(self):
        """运行辅助脚本列出最新导出文件并在日志区展示

        函数级注释：
        - 调用 scripts/list_latest_exports.py（支持任意工作目录运行）；
        - 默认展示前 10 条，并打印绝对路径；
        - 将脚本输出追加到日志区，便于快速定位导出文件。
        """
        try:
            python_bin = (self.var_python_bin.get().strip() or PYTHON_BIN)
            cmd = [python_bin, os.path.join(PROJECT_ROOT, "scripts", "list_latest_exports.py"), "-n", "10"]
            self._append_log("运行命令: " + self._quote_cmd(cmd))
            completed = subprocess.run(cmd, capture_output=True, text=True)
            if completed.returncode == 0:
                out = completed.stdout.strip()
                if out:
                    for line in out.splitlines():
                        self._append_log(line)
                try:
                    messagebox.showinfo("完成", "已在日志区显示最新导出文件列表")
                except Exception:
                    pass
            else:
                err = completed.stderr.strip() or completed.stdout.strip()
                self._append_log(f"查询失败: {err}")
                messagebox.showerror("错误", f"查询导出失败:\n{err}")
        except Exception as e:
            self._append_log(f"执行异常: {e}")
            try:
                messagebox.showerror("错误", str(e))
            except Exception:
                pass

    def _fetch_latest_exports(self, limit: int = 20) -> dict:
        """获取最新导出文件列表，优先调用本地配置服务接口，失败时回退到本地脚本。

        函数级注释：
        - 首选 GET http://localhost:8003/api/latest-exports?limit=<n>，返回结构形如：
          {"ok": true, "limit": n, "data": {"output": [...], "outputs": [...]}, "root": "..."}
        - 回退方案：直接复用 scripts/list_latest_exports.py 的工具函数（collect_files/describe_file），构建等价结构；
        - 为保证 UI 稳定性，任何异常均返回空结构并记录日志。
        """
        import urllib.request
        import urllib.error
        import ssl
        try:
            ctx = ssl.create_default_context()
            url = f"http://localhost:8003/api/latest-exports?limit={int(limit)}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("ok"):
                return data
        except urllib.error.URLError as e:
            self._append_log(f"最新导出接口不可用，回退到本地脚本：{e}")
        except Exception as e:
            self._append_log(f"最新导出接口异常：{e}")

        # 回退到本地脚本实现
        try:
            from scripts.list_latest_exports import get_project_root, collect_files, describe_file
            root = get_project_root()
            targets = [root / "output", root / "outputs"]
            result = {"ok": True, "limit": int(limit), "data": {}, "root": str(root)}
            for t in targets:
                files = collect_files(t, int(limit))
                items = []
                for p in files:
                    name, mtime_str = describe_file(p)
                    try:
                        mtime = p.stat().st_mtime
                    except Exception:
                        mtime = None
                    items.append({
                        "name": name,
                        "path": str(p.resolve()),
                        "dir": str(p.parent.resolve()),
                        "mtime": mtime,
                        "mtime_str": mtime_str.replace("mtime: ", ""),
                    })
                result["data"][t.name] = items
            return result
        except Exception as e:
            self._append_log(f"本地脚本回退失败：{e}")
            return {"ok": False, "limit": int(limit), "data": {"output": [], "outputs": []}}

    def on_open_latest_exports_window(self):
        """打开“最新导出列表”小窗（Toplevel + Treeview），支持刷新、访达中显示与打开文件。

        函数级注释：
        - 构建一个独立窗口，展示 output/ 与 outputs/ 中的最新文件；
        - 双击列表项默认执行“打开文件”，右侧按钮提供“访达中显示/打开/复制路径/复制文件名”；
        - 数据源优先使用配置服务接口，失败时回退到本地脚本；
        - 为避免重复创建，若窗口已存在则置顶并刷新。
        """
        if getattr(self, "_latest_win", None) is not None and self._latest_win.winfo_exists():
            try:
                self._latest_win.lift()
                self._refresh_latest_exports()
            except Exception:
                pass
            return

        win = tk.Toplevel(self.root)
        win.title("最新导出列表")
        win.geometry("900x420")
        self._latest_win = win

        # 上方工具栏
        toolbar = ttk.Frame(win)
        toolbar.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(toolbar, text="每目录条数:").pack(side=tk.LEFT)
        self._latest_limit_var = tk.StringVar(value="20")
        ttk.Entry(toolbar, textvariable=self._latest_limit_var, width=6).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Button(toolbar, text="刷新", command=self._refresh_latest_exports).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="访达中显示", command=lambda: self._act_on_selected(action="reveal")).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="打开文件", command=lambda: self._act_on_selected(action="open")).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="复制路径", command=self._copy_selected_path).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="复制文件名", command=self._copy_selected_name).pack(side=tk.LEFT, padx=4)

        # 列表区域（左右分栏：output 与 outputs）
        body = ttk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # output
        left_frame = ttk.LabelFrame(body, text="output")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self._tree_output = ttk.Treeview(left_frame, columns=("name", "mtime", "path"), show="headings")
        self._tree_output.heading("name", text="文件名")
        self._tree_output.heading("mtime", text="修改时间")
        self._tree_output.heading("path", text="路径")
        self._tree_output.column("name", width=200)
        self._tree_output.column("mtime", width=150)
        self._tree_output.column("path", width=400)
        self._tree_output.pack(fill=tk.BOTH, expand=True)
        self._tree_output.bind("<Double-1>", lambda _: self._act_on_selected(tree=self._tree_output, action="open"))
        # 右键菜单与列排序
        self._setup_tree_sorting(self._tree_output)
        self._attach_context_menu(self._tree_output)
        self._tree_output.bind("<Button-3>", lambda e: self._show_tree_context_menu(e, self._tree_output))
        self._tree_output.bind("<Button-2>", lambda e: self._show_tree_context_menu(e, self._tree_output))

        # outputs
        right_frame = ttk.LabelFrame(body, text="outputs")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree_outputs = ttk.Treeview(right_frame, columns=("name", "mtime", "path"), show="headings")
        self._tree_outputs.heading("name", text="文件名")
        self._tree_outputs.heading("mtime", text="修改时间")
        self._tree_outputs.heading("path", text="路径")
        self._tree_outputs.column("name", width=200)
        self._tree_outputs.column("mtime", width=150)
        self._tree_outputs.column("path", width=400)
        self._tree_outputs.pack(fill=tk.BOTH, expand=True)
        self._tree_outputs.bind("<Double-1>", lambda _: self._act_on_selected(tree=self._tree_outputs, action="open"))
        # 右键菜单与列排序
        self._setup_tree_sorting(self._tree_outputs)
        self._attach_context_menu(self._tree_outputs)
        self._tree_outputs.bind("<Button-3>", lambda e: self._show_tree_context_menu(e, self._tree_outputs))
        self._tree_outputs.bind("<Button-2>", lambda e: self._show_tree_context_menu(e, self._tree_outputs))

        # 初次加载
        self._refresh_latest_exports()

        # Esc 关闭窗口
        win.bind("<Escape>", lambda _: win.destroy())
        # 绑定快捷键
        self._bind_latest_shortcuts(win)

    def _refresh_latest_exports(self):
        """刷新最新导出窗口中的数据。

        函数级注释：
        - 读取 limit 输入框的值并进行容错（非法时回退 20）；
        - 调用 _fetch_latest_exports 获取数据；
        - 清空并填充两个 Treeview。
        """
        try:
            limit_raw = self._latest_limit_var.get().strip()
            limit = int(limit_raw) if limit_raw else 20
            if limit <= 0:
                limit = 20
        except Exception:
            limit = 20

        data = self._fetch_latest_exports(limit=limit)
        lists = (data.get("data") or {}) if isinstance(data, dict) else {}
        output_list = lists.get("output", [])
        outputs_list = lists.get("outputs", [])

        def fill(tree: ttk.Treeview, items: list):
            # 记录刷新前选中项（iid 为路径）
            try:
                prev_sel = set(tree.selection())
            except Exception:
                prev_sel = set()
            tree.delete(*tree.get_children())
            for it in items:
                name = it.get("name")
                mtime = it.get("mtime_str") or it.get("mtime")
                path = it.get("path")
                # 使用 path 作为 iid，方便后续定位选中行
                tree.insert("", tk.END, iid=str(path), values=(name, mtime, path))
            # 刷新后恢复选中项
            try:
                if prev_sel:
                    for iid in prev_sel:
                        if iid in tree.get_children(""):
                            tree.selection_add(iid)
            except Exception:
                pass

        fill(self._tree_output, output_list)
        fill(self._tree_outputs, outputs_list)

        # 若存在上次排序状态，刷新后继续应用
        try:
            for tree in (self._tree_output, self._tree_outputs):
                state = (self._tree_sort_state or {}).get(str(id(tree)))
                if state:
                    self._sort_tree(tree, state["col"], keep_order=state["ascending"])  # 按之前的顺序排序
        except Exception:
            pass

    def _get_active_tree(self) -> ttk.Treeview | None:
        """获取当前应当被操作的 Treeview（优先有选中项者，其次根据焦点）。

        函数级注释：
        - 若左右两侧均无选中项，则返回左侧 output；
        - 若任一侧有选中项，优先返回该侧；
        - 若焦点在某个 Treeview 上，也优先返回该侧。
        """
        try:
            # 优先检查选中项
            left_sel = self._tree_output.selection() if getattr(self, "_tree_output", None) else []
            right_sel = self._tree_outputs.selection() if getattr(self, "_tree_outputs", None) else []
            if right_sel:
                return self._tree_outputs
            if left_sel:
                return self._tree_output
            # 再检查焦点
            f = self.root.focus_get()
            if f and isinstance(f, ttk.Treeview):
                return f
        except Exception:
            pass
        return getattr(self, "_tree_output", None)

    def _bind_latest_shortcuts(self, win: tk.Toplevel):
        """为“最新导出列表”窗口绑定常用快捷键。

        函数级注释：
        - Enter：打开选中项（open）；
        - Ctrl/Cmd+R：刷新列表；
        - Ctrl/Cmd+C：复制选中路径；
        - Ctrl/Cmd+Shift+C：复制选中文件名；
        - O：打开；F：访达中显示；
        - 所有操作均依据当前活动 Treeview（有选中项或有焦点者）。
        """
        try:
            # 打开（Enter / o）
            win.bind("<Return>", lambda _: self._act_on_selected(tree=self._get_active_tree(), action="open"))
            win.bind("<o>", lambda _: self._act_on_selected(tree=self._get_active_tree(), action="open"))
            # 访达中显示（f）
            win.bind("<f>", lambda _: self._act_on_selected(tree=self._get_active_tree(), action="reveal"))
            # 刷新（Ctrl/Cmd+R）
            win.bind("<Control-r>", lambda _: self._refresh_latest_exports())
            win.bind("<Command-r>", lambda _: self._refresh_latest_exports())
            # 复制路径（Ctrl/Cmd+C）
            win.bind("<Control-c>", lambda _: self._copy_selected_path(tree=self._get_active_tree()))
            win.bind("<Command-c>", lambda _: self._copy_selected_path(tree=self._get_active_tree()))
            # 复制文件名（Ctrl/Cmd+Shift+C）
            win.bind("<Control-C>", lambda _: self._copy_selected_name(tree=self._get_active_tree()))
            win.bind("<Command-C>", lambda _: self._copy_selected_name(tree=self._get_active_tree()))
        except Exception:
            pass

    def _get_selected_item(self, tree: ttk.Treeview | None = None) -> dict | None:
        """获取当前选中的列表项（返回包含 name/path/mtime 信息的字典）。

        函数级注释：
        - 默认优先从左侧 output 列表获取选中项；
        - 若指定 tree 则从对应的 Treeview 获取；
        - 若无选中项则返回 None。
        """
        t = tree or self._tree_output
        if not t:
            return None
        sel = t.selection()
        if not sel:
            return None
        iid = sel[0]
        vals = t.item(iid, "values")
        if not vals or len(vals) < 3:
            return None
        return {"name": vals[0], "mtime": vals[1], "path": vals[2]}

    def _copy_selected_path(self, tree: ttk.Treeview | None = None):
        """复制选中文件的绝对路径到剪贴板。"""
        item = self._get_selected_item(tree=tree)
        if not item:
            messagebox.showinfo("提示", "请先选择一项")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(item["path"]) 
            messagebox.showinfo("已复制", "路径已复制到剪贴板")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")

    def _copy_selected_name(self, tree: ttk.Treeview | None = None):
        """复制选中文件名到剪贴板。"""
        item = self._get_selected_item(tree=tree)
        if not item:
            messagebox.showinfo("提示", "请先选择一项")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(item["name"]) 
            messagebox.showinfo("已复制", "文件名已复制到剪贴板")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")

    def _attach_context_menu(self, tree: ttk.Treeview):
        """为指定 Treeview 创建并挂载右键上下文菜单。

        函数级注释：
        - 菜单包含：打开文件、访达中显示、复制路径、复制文件名；
        - 绑定在 tree 对象上，属性名为 _context_menu_<id>，避免重复创建；
        - 菜单回调基于当前选中项执行。
        """
        try:
            key = f"_context_menu_{id(tree)}"
            if getattr(self, key, None):
                return
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="打开文件", command=lambda: self._act_on_selected(tree=tree, action="open"))
            menu.add_command(label="访达中显示", command=lambda: self._act_on_selected(tree=tree, action="reveal"))
            menu.add_separator()
            menu.add_command(label="复制路径", command=lambda: self._copy_selected_path(tree=tree))
            menu.add_command(label="复制文件名", command=lambda: self._copy_selected_name(tree=tree))
            setattr(self, key, menu)
        except Exception:
            pass

    def _show_tree_context_menu(self, event, tree: ttk.Treeview):
        """在鼠标位置显示指定 Treeview 的右键菜单。"""
        try:
            key = f"_context_menu_{id(tree)}"
            menu = getattr(self, key, None)
            if not menu:
                return
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _setup_tree_sorting(self, tree: ttk.Treeview):
        """为 Treeview 的列头绑定点击排序事件。

        函数级注释：
        - 点击列头触发排序（name/mtime/path）；
        - mtime 列可直接按字符串排序（YYYY-MM-DD HH:MM:SS），与时间顺序一致；
        - 再次点击同列将切换升/降序。
        """
        try:
            for col in ("name", "mtime", "path"):
                tree.heading(col, command=lambda c=col: self._sort_tree(tree, c))
        except Exception:
            pass

    def _sort_tree(self, tree: ttk.Treeview, col: str, keep_order: bool | None = None):
        """对指定 Treeview 的列数据进行排序，并重新排列行。

        参数：
          - tree: 目标 Treeview
          - col: 列名（name/mtime/path）
          - keep_order: 若为 True/False，强制使用该顺序；若为 None，则切换为上次相反的顺序。

        行为：
          - 读取所有行的 values，根据 col 提取比较键；
          - 按 ascending 顺序排序并重新移动项；
          - 记录排序状态到 self._tree_sort_state，便于刷新后保持顺序。
        """
        try:
            # 初始化排序状态容器
            if not hasattr(self, "_tree_sort_state"):
                self._tree_sort_state = {}
            key = str(id(tree))
            state = self._tree_sort_state.get(key) or {"col": col, "ascending": True}
            ascending = state["ascending"] if keep_order is None else bool(keep_order)
            # 若点击不同列，默认重置为升序
            if keep_order is None and state.get("col") != col:
                ascending = True

            # 收集条目
            items = []
            for iid in tree.get_children(""):
                vals = tree.item(iid, "values")
                if not vals or len(vals) < 3:
                    continue
                # 列索引映射
                idx = {"name": 0, "mtime": 1, "path": 2}[col]
                items.append((iid, vals[idx], vals))

            # 排序：字符串直接比较即可（mtime_str 格式）
            items.sort(key=lambda x: x[1] or "", reverse=not ascending)

            # 重新放置
            for pos, (iid, _, _) in enumerate(items):
                tree.move(iid, "", pos)

            # 更新列头指示（简单用字符标记）
            arrow = "↑" if ascending else "↓"
            try:
                tree.heading(col, text={"name": "文件名", "mtime": "修改时间", "path": "路径"}[col] + f" {arrow}")
            except Exception:
                pass

            # 记录状态
            self._tree_sort_state[key] = {"col": col, "ascending": ascending}
        except Exception:
            pass

    def _act_on_selected(self, tree: ttk.Treeview | None = None, action: str = "reveal"):
        """对选中项执行操作：访达中显示(reveal)或打开(open)。

        函数级注释：
        - 通过 POST /api/open-path 调用后端的 Finder 操作；
        - 后端已做路径安全校验（仅 output/ 与 outputs/），此处只负责转发；
        - 若服务不可用或返回失败，弹窗提示。
        """
        item = self._get_selected_item(tree=tree)
        if not item:
            messagebox.showinfo("提示", "请先选择一项")
            return
        path = item.get("path")
        if not path:
            messagebox.showwarning("提示", "无效的路径")
            return
        self._open_path_in_finder(path, action)

    def _open_path_in_finder(self, path: str, action: str = "reveal"):
        """调用配置服务接口在 macOS Finder 中显示或打开目标路径。

        函数级注释：
        - POST http://localhost:8003/api/open-path，body: {path, action};
        - 成功时提示并不阻塞；失败时弹窗显示原因（例如路径不安全或非 macOS）。
        """
        import urllib.request
        import urllib.error
        import ssl
        try:
            ctx = ssl.create_default_context()
            url = "http://localhost:8003/api/open-path"
            payload = json.dumps({"path": path, "action": action}).encode("utf-8")
            req = urllib.request.Request(url, method="POST", data=payload)
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("ok"):
                messagebox.showinfo("成功", data.get("message", "已在访达中处理"))
            else:
                message = (data.get("message") if isinstance(data, dict) else None) or "操作失败"
                messagebox.showerror("错误", message)
        except urllib.error.URLError as e:
            messagebox.showerror("错误", f"无法连接配置服务: {e}")
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {e}")

    def on_detect_python(self):
        """自动检测当前 GUI 所使用的 Python 解释器路径并回填到输入框

        函数级注释：
        - 使用 sys.executable 获取当前进程的解释器；
        - 对 macOS 用户通常返回 /usr/bin/python3 或 Homebrew/虚拟环境路径；
        - 检测成功后更新 var_python_bin 并提示。
        """
        try:
            detected = sys.executable
            if detected:
                self.var_python_bin.set(detected)
                try:
                    messagebox.showinfo("已检测", f"Python 路径: {detected}")
                except Exception:
                    pass
            else:
                messagebox.showwarning("提示", "未能检测到 Python 路径，请手动填写")
        except Exception as e:
            messagebox.showerror("错误", f"检测失败: {e}")

    def on_save_config(self):
        """保存当前 UI 配置到项目根目录，同时生成 CLI 可直接读取的配置文件

        函数级注释：
        - 保存 UI 配置到 ui_config.json（便于界面恢复，包括 python_bin）；
        - 生成 config.json（结构化 app/ocr/output），供 CLI 的 ConfigManager 自动读取；
        - 使用 ensure_ascii=False 保留中文；若写入任一文件失败，提示错误但不影响另一个文件的保存。
        """
        # 1) 保存 UI 配置
        ui_cfg_path = os.path.join(PROJECT_ROOT, "ui_config.json")
        ui_data = {
            "python_bin": self.var_python_bin.get(),
            "window_title": self.var_window_title.get(),
            "chat_area": self.var_chat_area.get(),
            "direction": self.var_direction.get(),
            "full_fetch": self.var_full_fetch.get(),
            "go_top_first": self.var_go_top_first.get(),
            "skip_empty": self.var_skip_empty.get(),
            "verbose": self.var_verbose.get(),
            "ocr_lang": self.var_ocr_lang.get(),
            "output_dir": self.var_output_dir.get(),
            "filename_prefix": self.var_filename_prefix.get(),
            "scroll_delay": self.var_scroll_delay.get(),
            "max_scrolls": self.var_max_scrolls.get(),
            "max_spm": self.var_max_spm.get(),
            "formats": {name: var.get() for name, var in self.format_vars.items()},
        }
        ui_save_ok = False
        try:
            with open(ui_cfg_path, "w", encoding="utf-8") as f:
                json.dump(ui_data, f, ensure_ascii=False, indent=2)
            ui_save_ok = True
        except Exception as e:
            messagebox.showerror("错误", f"保存 UI 配置失败: {e}")

        # 2) 生成 CLI 使用的 config.json
        cfg_path = os.path.join(PROJECT_ROOT, "config.json")
        # 选择一个主导出格式（若多选，取首个勾选的，否则 json）
        chosen_formats = [name for name, var in self.format_vars.items() if var.get()]
        primary_format = chosen_formats[0] if chosen_formats else "json"
        try:
            # 将 UI 值映射到 AppConfig 所需结构（保持合理默认）
            scroll_delay_val = None
            try:
                sd = self.var_scroll_delay.get().strip()
                scroll_delay_val = float(sd) if sd else None
            except Exception:
                scroll_delay_val = None
            config_data = {
                "app": {
                    "scroll_speed": 2,
                    "scroll_delay": scroll_delay_val if scroll_delay_val is not None else 1.0,
                    "max_retry_attempts": 3,
                },
                "ocr": {
                    "language": self.var_ocr_lang.get().strip() or "ch",
                    "confidence_threshold": 0.7,
                },
                "output": {
                    "format": primary_format,
                    "directory": self.var_output_dir.get().strip() or os.path.join(PROJECT_ROOT, "output"),
                    "enable_deduplication": True,
                    "formats": chosen_formats,
                }
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            if ui_save_ok:
                messagebox.showinfo("已保存", f"配置已保存：\n- UI: {ui_cfg_path}\n- CLI: {cfg_path}")
            else:
                messagebox.showinfo("已保存", f"CLI 配置已保存到: {cfg_path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存 CLI 配置失败: {e}")

    def on_load_config(self):
        """从项目根目录 ui_config.json 加载配置并回填到 UI

        函数级注释：
        - 若文件存在，读取 JSON 并设置各字段与复选框；
        - 兼容 python_bin 字段（若存在则回填解释器路径）；
        - 若不存在，提示用户先保存一次配置。
        """
        cfg_path = os.path.join(PROJECT_ROOT, "ui_config.json")
        if not os.path.exists(cfg_path):
            messagebox.showinfo("提示", "未找到配置文件，请先保存配置")
            return
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.var_python_bin.set(data.get("python_bin", self.var_python_bin.get()))
            self.var_window_title.set(data.get("window_title", ""))
            self.var_chat_area.set(data.get("chat_area", ""))
            self.var_direction.set(data.get("direction", "up"))
            self.var_full_fetch.set(bool(data.get("full_fetch", False)))
            self.var_go_top_first.set(bool(data.get("go_top_first", False)))
            self.var_skip_empty.set(bool(data.get("skip_empty", True)))
            self.var_verbose.set(bool(data.get("verbose", True)))
            self.var_ocr_lang.set(data.get("ocr_lang", "ch"))
            self.var_output_dir.set(data.get("output_dir", os.path.join(PROJECT_ROOT, "output")))
            self.var_filename_prefix.set(data.get("filename_prefix", "auto_wechat_scan"))
            self.var_scroll_delay.set(str(data.get("scroll_delay", "")))
            self.var_max_scrolls.set(str(data.get("max_scrolls", "60")))
            self.var_max_spm.set(str(data.get("max_spm", "40")))
            formats_data = data.get("formats", {})
            for name, var in self.format_vars.items():
                var.set(bool(formats_data.get(name, var.get())))
            messagebox.showinfo("已加载", "配置已回填到界面")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {e}")

    def on_load_from_server(self):
        """从本地配置服务加载 UI 配置并回填到界面

        函数级注释：
        - 调用 GET http://localhost:8003/api/load-config 获取 ui_config.json 的内容；
        - 若服务未启动或响应异常，给出友好提示；
        - 字段映射同 on_load_config，确保行为一致。
        """
        import urllib.request
        import urllib.error
        import ssl

        url = "http://localhost:8003/api/load-config"
        try:
            # 兼容可能的自签名，本地仅用于开发
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if not data or not data.get("ok"):
                message = data.get("message", "服务返回失败") if isinstance(data, dict) else "服务返回失败"
                messagebox.showerror("错误", message)
                return
            payload = data.get("data") or {}
            # 与 on_load_config 同步字段回填逻辑
            self.var_python_bin.set(payload.get("python_bin", self.var_python_bin.get()))
            self.var_window_title.set(payload.get("window_title", ""))
            self.var_chat_area.set(payload.get("chat_area", ""))
            self.var_direction.set(payload.get("direction", "up"))
            self.var_full_fetch.set(bool(payload.get("full_fetch", False)))
            self.var_go_top_first.set(bool(payload.get("go_top_first", False)))
            self.var_skip_empty.set(bool(payload.get("skip_empty", True)))
            self.var_verbose.set(bool(payload.get("verbose", True)))
            self.var_ocr_lang.set(payload.get("ocr_lang", "ch"))
            self.var_output_dir.set(payload.get("output_dir", os.path.join(PROJECT_ROOT, "output")))
            self.var_filename_prefix.set(payload.get("filename_prefix", "auto_wechat_scan"))
            self.var_scroll_delay.set(str(payload.get("scroll_delay", "")))
            self.var_max_scrolls.set(str(payload.get("max_scrolls", "60")))
            self.var_max_spm.set(str(payload.get("max_spm", "40")))
            formats_data = payload.get("formats", {})
            for name, var in self.format_vars.items():
                var.set(bool(formats_data.get(name, var.get())))
            messagebox.showinfo("已加载", "已从配置服务回填界面")
        except urllib.error.URLError as e:
            messagebox.showerror("错误", f"无法连接配置服务: {e}")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {e}")


def main():
    """程序入口：构建并启动 Tkinter 主循环"""
    root = tk.Tk()
    app = SimpleWechatGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
