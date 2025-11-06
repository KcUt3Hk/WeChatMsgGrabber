#!/Users/pankkkk/Projects/Setting/python_envs/bin/python3.12
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
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List

from PIL import Image, ImageTk


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_BIN = "/Users/pankkkk/Projects/Setting/python_envs/bin/python3.12"


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

        # 字段变量
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

        self.format_vars = {
            "json": tk.BooleanVar(value=True),
            "csv": tk.BooleanVar(value=True),
            "md": tk.BooleanVar(value=False),
            "txt": tk.BooleanVar(value=False),
        }

        self._build_layout()

    def _build_layout(self):
        """构建界面布局与控件"""
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # 第一行：窗口标题、聊天区域
        row = 0
        ttk.Label(frm, text="窗口标题（可选）:").grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_window_title, width=32).grid(row=row, column=1, sticky=tk.W)
        ttk.Label(frm, text="聊天区域坐标 x,y,w,h（可选）:").grid(row=row, column=2, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_chat_area, width=24).grid(row=row, column=3, sticky=tk.W)
        ttk.Button(frm, text="预览聊天区域", command=self.on_preview_chat_area).grid(row=row, column=4, sticky=tk.W)

        # 第二行：滚动与 OCR
        row += 1
        ttk.Label(frm, text="方向:").grid(row=row, column=0, sticky=tk.W)
        ttk.Combobox(frm, textvariable=self.var_direction, values=["up", "down"], width=6, state="readonly").grid(row=row, column=1, sticky=tk.W)
        ttk.Label(frm, text="scroll-delay（秒，可空）:").grid(row=row, column=2, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_scroll_delay, width=8).grid(row=row, column=3, sticky=tk.W)
        ttk.Label(frm, text="OCR 语言:").grid(row=row, column=4, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_ocr_lang, width=6).grid(row=row, column=5, sticky=tk.W)

        # 第三行：阈值与开关
        row += 1
        ttk.Label(frm, text="max-scrolls:").grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_max_scrolls, width=6).grid(row=row, column=1, sticky=tk.W)
        ttk.Label(frm, text="每分钟滚动 (spm):").grid(row=row, column=2, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_max_spm, width=6).grid(row=row, column=3, sticky=tk.W)
        ttk.Checkbutton(frm, text="full-fetch", variable=self.var_full_fetch).grid(row=row, column=4, sticky=tk.W)
        ttk.Checkbutton(frm, text="go-top-first", variable=self.var_go_top_first).grid(row=row, column=5, sticky=tk.W)

        # 第四行：导出与目录
        row += 1
        ttk.Label(frm, text="导出格式:").grid(row=row, column=0, sticky=tk.W)
        col = 1
        for name in ["json", "csv", "md", "txt"]:
            ttk.Checkbutton(frm, text=name, variable=self.format_vars[name]).grid(row=row, column=col, sticky=tk.W)
            col += 1
        ttk.Label(frm, text="输出目录:").grid(row=row, column=4, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_output_dir, width=24).grid(row=row, column=5, sticky=tk.W)
        ttk.Button(frm, text="选择…", command=self.on_choose_output).grid(row=row, column=6, sticky=tk.W)

        # 第五行：文件名前缀与开关
        row += 1
        ttk.Label(frm, text="文件前缀:").grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.var_filename_prefix, width=20).grid(row=row, column=1, sticky=tk.W)
        ttk.Checkbutton(frm, text="skip-empty", variable=self.var_skip_empty).grid(row=row, column=2, sticky=tk.W)
        ttk.Checkbutton(frm, text="verbose", variable=self.var_verbose).grid(row=row, column=3, sticky=tk.W)
        ttk.Button(frm, text="打开输出目录", command=self.on_open_output).grid(row=row, column=4, sticky=tk.W)

        # 第六行：操作按钮
        row += 1
        ttk.Button(frm, text="开始扫描", command=self.on_start_scan).grid(row=row, column=0, sticky=tk.W)
        ttk.Button(frm, text="退出", command=self.root.quit).grid(row=row, column=1, sticky=tk.W)

        # 预览图与日志
        row += 1
        self.preview_label = ttk.Label(frm, text="预览图将在此显示")
        self.preview_label.grid(row=row, column=0, columnspan=3, sticky=tk.W)
        self.log_text = tk.Text(frm, height=20, width=120)
        self.log_text.grid(row=row, column=3, columnspan=4, sticky=tk.W)

    def _get_formats(self) -> str:
        """收集导出格式复选框，拼接为逗号分隔字符串"""
        chosen: List[str] = [name for name, var in self.format_vars.items() if var.get()]
        return ",".join(chosen) if chosen else "json"

    def _build_scan_command(self) -> List[str]:
        """根据界面参数构建 auto_wechat_scan.py 的命令行列表"""
        cmd = [PYTHON_BIN, os.path.join(PROJECT_ROOT, "cli", "auto_wechat_scan.py")]
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
        return cmd

    def _append_log(self, text: str):
        """将文本追加到日志区域并滚动到底部"""
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def on_start_scan(self):
        """启动扫描：在后台线程中执行命令并实时输出日志"""
        cmd = self._build_scan_command()
        self._append_log("运行命令: " + " ".join(cmd))

        def worker():
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    self._append_log(line.rstrip())
                code = proc.wait()
                self._append_log(f"进程退出码: {code}")
                if code == 0:
                    messagebox.showinfo("完成", "扫描完成")
                else:
                    messagebox.showwarning("警告", f"扫描退出码: {code}")
            except Exception as e:
                self._append_log(f"执行失败: {e}")
                messagebox.showerror("错误", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def on_preview_chat_area(self):
        """生成聊天区域预览图：调用 capture_rect_preview 并在界面显示"""
        rect = self.var_chat_area.get().strip()
        if not rect:
            messagebox.showinfo("提示", "请先输入聊天区域坐标，例如 120,80,920,900")
            return
        out_png = os.path.join(PROJECT_ROOT, "outputs", "debug_chat_area_preview.png")
        cmd = [PYTHON_BIN, os.path.join(PROJECT_ROOT, "scripts", "capture_rect_preview.py"), "--rect", rect, "--out", out_png]
        try:
            subprocess.run(cmd, check=True)
            img = Image.open(out_png)
            img.thumbnail((400, 400))
            self.preview_image = ImageTk.PhotoImage(img)
            self.preview_label.configure(image=self.preview_image)
            self.preview_label.image = self.preview_image
            self._append_log(f"预览已保存: {out_png}")
        except subprocess.CalledProcessError as e:
            messagebox.showerror("错误", f"预览失败: {e}")
        except Exception as e:
            messagebox.showerror("错误", f"预览异常: {e}")

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


def main():
    """程序入口：构建并启动 Tkinter 主循环"""
    root = tk.Tk()
    app = SimpleWechatGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()