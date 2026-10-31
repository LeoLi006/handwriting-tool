# coding: utf-8
r"""
手写体转换器 - 图形界面
把 Word / Markdown / TXT 文件拖进窗口即可转成手写体 PNG 图片。

运行:
    python 手写体工具/gui.py     (或双击 启动GUI.bat)

依赖: handright, fonttools, pillow, tkinterdnd2, matplotlib
"""

import os
import queue
import sys
import threading
import traceback
import warnings
import tempfile
import webbrowser

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_OK = True
except Exception:
    DND_OK = False

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import handwriting as hw   # noqa: E402
from app_settings import PRESETS, load_settings, save_settings
from batch_tasks import run_batch
import font_manager

ACCENT = "#29796b"
BG = "#f2f4f3"
CARD = "#ffffff"
INK = "#243c36"
MUTED = "#71817b"

FONT_LABELS = {
    "WenKai": "霞鹜文楷（工整·默认）",
    "MaShanZheng": "马善政墨韵（毛笔楷书）",
    "LongCang": "龙藏体（硬笔行书）",
    "LiuJianMaoCao": "六剑毛笔草（草书）",
    "ZhiMangXing": "志莽行书（行书）",
    "ZCOOLKuaiLe": "站酷快乐体（卡通）",
    "Xiaolai": "小赖字体（轻松手写）",
    "YozaiLight": "悠哉细体（轻盈）",
    "Yozai": "悠哉字体（随性手写）",
    "YozaiMedium": "悠哉中等（较粗）",
    "MarkerGothic": "霞鹜漫黑（马克笔风格）",
    "ZhenKai": "霞鹜臻楷（楷书风格）",
}
# 公式字体（需要符号齐全，matplotlib mathtext 用它渲染二维公式）
FORMULA_FONT_LABELS = {
    "WenKai": "霞鹜文楷（推荐·符号最全）",
    "MaShanZheng": "马善政墨韵",
    "LongCang": "龙藏体",
    "LiuJianMaoCao": "六剑毛笔草",
    "ZhiMangXing": "志莽行书",
    "ZCOOLKuaiLe": "站酷快乐体",
    "Xiaolai": "小赖字体",
    "YozaiLight": "悠哉细体",
    "Yozai": "悠哉字体",
    "YozaiMedium": "悠哉中等",
    "MarkerGothic": "霞鹜漫黑",
    "ZhenKai": "霞鹜臻楷",
}


class App:
    def __init__(self, root, settings_file=None):
        self.root = root
        self.settings_file = settings_file
        self._save_id = None
        self._applying = False
        self._approved_snapshot = None
        self._preview_dir = tempfile.TemporaryDirectory(prefix='mojian-preview-')
        self.cancel_event = threading.Event()
        self.jobs = []
        self._closing = False
        # Use consistent widget dimensions across Python/Tk builds on Windows.
        self.root.tk.call('tk', 'scaling', 96 / 72)
        self.files = []
        self.preview_img = None
        self.busy = False
        self.output_paths = []
        self.preview_index = 0
        self.notices = []
        self.q = queue.Queue()      # worker 线程 -> 主线程 的消息队列

        root.title("墨笺 · 手写体转换器")
        root.geometry("1080x800")
        root.minsize(900, 620)
        root.configure(bg=BG)

        self._build_style()
        self._build_layout()
        self._load_preferences()
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self.root.after(80, self._poll)   # 主线程轮询队列

    # ------------------------------------------------------------------ UI
    def _build_style(self):
        st = ttk.Style()
        st.theme_use("clam")
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))
        st.configure("TLabel", background=CARD, foreground=INK)
        st.configure("Muted.TLabel", foreground=MUTED)
        st.configure("TFrame", background=CARD)
        st.configure("TButton", padding=(12, 8), background="#edf3f0", foreground=INK,
                     borderwidth=0)
        st.map("TButton", background=[("active", "#dce9e3")])
        st.configure("Primary.TButton", background=ACCENT, foreground="white",
                     font=("Microsoft YaHei UI", 10, "bold"))
        st.map("Primary.TButton", background=[("disabled", "#a9bdb6"), ("active", "#216557")],
               foreground=[("disabled", "#f2f4f3")])
        st.configure("TCombobox", padding=5, fieldbackground="white", arrowsize=14)
        st.configure("TEntry", padding=6, fieldbackground="white")
        st.configure("TCheckbutton", background=CARD, foreground=INK, padding=(0, 4))
        st.map("TCheckbutton", background=[("active", CARD)])
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e8eeeb",
                     borderwidth=0, thickness=5)

    def _build_layout(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 14))
        tk.Label(header, text="墨笺", bg=BG, fg=INK,
                 font=("Microsoft YaHei UI", 24, "bold")).pack(side="left")
        tk.Label(header, text="把文档，写成你的笔记", bg=BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 11)).pack(side="left", padx=18, pady=(10, 0))
        tk.Label(header, text="本地转换  ·  PNG / PDF", bg=BG, fg=ACCENT).pack(side="right", pady=(10, 0))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        panel = tk.Frame(body, bg=CARD, width=330)
        panel.pack(side="left", fill="y", padx=(0, 18))
        panel.pack_propagate(False)
        # Keep the conversion button visible even when the settings need scrolling.
        actions = tk.Frame(panel, bg=CARD)
        actions.pack(side="bottom", fill="x", padx=18, pady=16)
        self.preview_btn = ttk.Button(actions, text='快速预览第一页', command=self._preview_one)
        self.preview_btn.pack(fill='x', pady=(0, 6))
        self.go_btn = ttk.Button(actions, text="确认生成全文", style="Primary.TButton",
                                 command=self._start, state='disabled')
        self.go_btn.pack(fill="x")
        self.cancel_btn = ttk.Button(actions, text='取消当前批次', command=self.cancel_event.set, state='disabled')
        self.cancel_btn.pack(fill='x', pady=(6, 0))
        self.prog = ttk.Progressbar(actions, mode="determinate")
        self.prog.pack(fill="x", pady=(10, 0))
        settings = tk.Frame(panel, bg=CARD)
        settings.pack(fill="both", expand=True, pady=(16, 0))
        scroll = tk.Canvas(settings, bg=CARD, highlightthickness=0, width=300)
        bar = ttk.Scrollbar(settings, orient="vertical", command=scroll.yview)
        bar.pack(side="right", fill="y")
        scroll.pack(side="left", fill="both", expand=True)
        scroll.configure(yscrollcommand=bar.set)
        left = tk.Frame(scroll, bg=CARD, padx=18)
        window = scroll.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>", lambda e: scroll.itemconfigure(window, width=e.width))
        def wheel(event):
            if str(event.widget).startswith(str(panel)) and event.delta:
                scroll.yview_scroll(-1 if event.delta > 0 else 1, "units")
        self.root.bind("<MouseWheel>", wheel, add="+")

        def section(title, subtitle=None):
            tk.Label(left, text=title, bg=CARD, fg=INK, anchor="w",
                     font=("Microsoft YaHei UI", 11, "bold")).pack(fill="x", pady=(8, 4))
            if subtitle:
                tk.Label(left, text=subtitle, bg=CARD, fg=MUTED, anchor="w",
                         font=("Microsoft YaHei UI", 9)).pack(fill="x", pady=(0, 8))
        def caption(text):
            ttk.Label(left, text=text).pack(anchor="w", pady=(7, 3))
        def divider():
            tk.Frame(left, bg="#e9efeb", height=1).pack(fill="x", pady=(14, 6))

        section("常用预设", "自动记住你的调整")
        self.preset_var = tk.StringVar(value='自定义')
        presets = ttk.Combobox(left, textvariable=self.preset_var, state='readonly',
                               values=['自定义', *PRESETS])
        presets.pack(fill='x', pady=(0, 10))
        presets.bind('<<ComboboxSelected>>', lambda e: self._apply_preset())
        section("字体与排版", "选择字迹，调整纸上的疏密")
        self.font_var = tk.StringVar()
        self.font_combo = ttk.Combobox(left, textvariable=self.font_var, state="readonly")
        self.font_combo.pack(fill="x", pady=(0, 6)); self._load_fonts()
        ttk.Button(left, text='字体管理 · 样张与按需下载', command=self._font_manager).pack(fill='x', pady=(0, 5))
        caption("字号")
        self.size_var = tk.IntVar(value=40); self._slider(left, self.size_var, 24, 64, None)
        caption("行距")
        self.line_var = tk.DoubleVar(value=1.4); self._slider(left, self.line_var, 0.9, 2.6, None, 0.05)
        caption("字距")
        self.word_var = tk.DoubleVar(value=0); self._slider(left, self.word_var, -10, 16, None)
        divider()
        section("手写变化", "整齐程度与字形变化，分别调整")
        caption("位置 / 旋转随机度")
        self.jitter_var = tk.DoubleVar(value=0.2); self._slider(left, self.jitter_var, 0, 2.5, None, 0.1)
        caption("字形变化强度")
        self.glyph_variation_var = tk.DoubleVar(value=1); self._slider(left, self.glyph_variation_var, 0, 1.8, None, 0.1)
        divider()
        section("纸张与公式")
        self.ruled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="横线本背景", variable=self.ruled_var).pack(anchor="w")
        self.formula_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="二维数学公式", variable=self.formula_var).pack(anchor="w")
        caption("公式字体")
        self.formula_font_var = tk.StringVar()
        self.fmfont_combo = ttk.Combobox(left, textvariable=self.formula_font_var, state="readonly")
        self.fmfont_combo.pack(fill="x"); self._load_formula_fonts()
        divider()
        section("保存位置", "留空则保存到源文件旁的「手写体」")
        row = tk.Frame(left, bg=CARD); row.pack(fill="x", pady=(2, 12))
        self.out_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.out_var, width=14).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="选择", width=4, command=self._choose_out).pack(side="right", padx=(5, 0))
        section('导出格式')
        self.export_var = tk.StringVar(value='PNG 图片')
        ttk.Combobox(left, textvariable=self.export_var, state='readonly',
                     values=['PNG 图片', 'PNG + PDF']).pack(fill='x', pady=(0, 14))

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        upload = tk.Frame(right, bg=CARD, padx=20, pady=16)
        upload.pack(fill="x")
        self.drop = tk.Label(upload, text="选择文档 → 预览 → 确认生成", bg="#f0f6f2", fg=ACCENT,
                             font=("Microsoft YaHei UI", 14, "bold"), cursor="hand2", pady=18)
        self.drop.pack(fill="x")
        self.drop.bind("<Button-1>", lambda e: self._choose_files())
        self.drop.bind("<Enter>", lambda e: self.drop.configure(bg="#e3efe8"))
        self.drop.bind("<Leave>", lambda e: self.drop.configure(bg="#f0f6f2"))
        row = tk.Frame(upload, bg=CARD); row.pack(fill="x", pady=(12, 0))
        tk.Label(row, text="Word .docx / Markdown / TXT · 可多选", bg=CARD, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        ttk.Button(row, text="选择文件", command=self._choose_files).pack(side="right")
        if DND_OK:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
        else:
            self.drop.configure(text="点击选择文档，先预览第一页")

        queue_card = tk.Frame(right, bg=CARD, padx=12, pady=8)
        queue_card.pack(fill='x', pady=(12, 0))
        queue_bar = tk.Frame(queue_card, bg=CARD); queue_bar.pack(fill='x')
        ttk.Label(queue_bar, text='文件队列 · 双击查看结果与问题').pack(side='left')
        self.retry_btn = ttk.Button(queue_bar, text='只重试失败项', command=self._retry_failed, state='disabled')
        self.retry_btn.pack(side='right')
        tree_frame = tk.Frame(queue_card, bg=CARD); tree_frame.pack(fill='x', pady=(5, 0))
        self.job_tree = ttk.Treeview(tree_frame, columns=('name', 'status'), show='headings', height=3)
        self.job_tree.heading('name', text='文档'); self.job_tree.heading('status', text='状态')
        self.job_tree.column('name', width=330); self.job_tree.column('status', width=120, stretch=False)
        queue_scroll = ttk.Scrollbar(tree_frame, command=self.job_tree.yview)
        queue_scroll.pack(side='right', fill='y')
        self.job_tree.configure(yscrollcommand=queue_scroll.set)
        self.job_tree.pack(side='left', fill='x', expand=True)
        self.job_tree.bind('<Double-1>', self._job_detail)

        preview_card = tk.Frame(right, bg=CARD, padx=16, pady=12)
        preview_card.pack(fill="both", expand=True, pady=(14, 0))
        toolbar = tk.Frame(preview_card, bg=CARD); toolbar.pack(fill="x", pady=(0, 10))
        tk.Label(toolbar, text="纸张预览", bg=CARD, fg=INK,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        ttk.Button(toolbar, text="打开输出目录", command=self._open_out).pack(side="right")
        self.preview = tk.Label(preview_card, bg="#e9eeeb", fg=MUTED,
                                text="选择文档后预览第一页\n\n满意后再确认生成全文", font=("Microsoft YaHei UI", 12))
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", self._resize_preview)
        nav = tk.Frame(preview_card, bg=CARD); nav.pack(fill="x", pady=(8, 0))
        self.prev_btn = ttk.Button(nav, text="上一页", command=lambda: self._turn_page(-1), state="disabled")
        self.prev_btn.pack(side="left")
        self.page_label = ttk.Label(nav, text="尚无页面", anchor="center")
        self.page_label.pack(side="left", fill="x", expand=True)
        self.next_btn = ttk.Button(nav, text="下一页", command=lambda: self._turn_page(1), state="disabled")
        self.next_btn.pack(side="right")
        self.status = tk.Label(right, text="就绪 · 所有文档在本机处理", bg=BG, fg=MUTED,
                               anchor="w", justify="left", wraplength=580, font=("Microsoft YaHei UI", 9))
        self.status.pack(fill="x", pady=(10, 0))

    def _slider(self, parent, var, lo, hi, cb, step=None):
        s = tk.Scale(parent, from_=lo, to=hi, orient="horizontal", variable=var,
                     resolution=step if step is not None else 1, bg=CARD, fg=MUTED,
                     highlightthickness=0, bd=0, relief="flat", sliderrelief="flat",
                     troughcolor="#e4ece7", activebackground=ACCENT, width=5,
                     sliderlength=18, length=240, command=(lambda e: cb()) if cb else None)
        s.pack(fill="x")
        return s

    def _load_fonts(self):
        reg = hw.load_registry()
        self.style_keys = list(reg.keys())
        labels = [FONT_LABELS.get(k, k) + (' · 待下载' if not font_manager.installed(k) else '') for k in self.style_keys]
        self.font_combo["values"] = labels
        if labels:
            default = "WenKai" if "WenKai" in self.style_keys else self.style_keys[0]
            self.font_combo.current(self.style_keys.index(default))

    def _setting_variables(self):
        return dict(font_size=self.size_var, line_spacing_ratio=self.line_var,
                    word_spacing=self.word_var, jitter=self.jitter_var,
                    glyph_variation=self.glyph_variation_var, ruled=self.ruled_var,
                    formula=self.formula_var, outdir=self.out_var, export_format=self.export_var)

    def _load_preferences(self):
        data = load_settings(self.settings_file)
        for key, var in self._setting_variables().items():
            if key in data:
                var.set(data[key])
        for key, combo in [('font', self.font_combo), ('formula_font', self.fmfont_combo)]:
            if data.get(key) in self.style_keys:
                combo.current(self.style_keys.index(data[key]))
        self.preset_var.set(data.get('preset', '自定义'))
        for var in [*self._setting_variables().values(), self.font_var, self.formula_font_var]:
            var.trace_add('write', self._settings_changed)

    def _settings_changed(self, *args):
        self._approved_snapshot = None
        self.go_btn.configure(state='disabled')
        if self.files and not self.busy:
            self.status.configure(text='设置已更新，请先快速预览，再确认生成。')
        output_variables = {str(self.out_var), str(self.export_var)}
        if not self._applying and (not args or args[0] not in output_variables):
            self.preset_var.set('自定义')
        if self._save_id:
            self.root.after_cancel(self._save_id)
        self._save_id = self.root.after(400, self._save_preferences)

    def _save_preferences(self):
        self._save_id = None
        data = {key: var.get() for key, var in self._setting_variables().items()}
        data.update(font=self.style_keys[self.font_combo.current()],
                    formula_font=self.style_keys[self.fmfont_combo.current()],
                    preset=self.preset_var.get())
        try:
            save_settings(data, self.settings_file)
        except OSError as exc:
            self.status.configure(text=f'设置未能保存：{exc}')

    def _apply_preset(self):
        data = PRESETS.get(self.preset_var.get())
        if not data:
            return
        self._applying = True
        try:
            for key, value in data.items():
                if key == 'font':
                    self.font_combo.current(self.style_keys.index(value if font_manager.installed(value) else 'WenKai'))
                elif key in self._setting_variables():
                    self._setting_variables()[key].set(value)
        finally:
            self._applying = False
        self._settings_changed_preset()

    def _settings_changed_preset(self):
        self._save_preferences()

    def _close(self):
        self._save_preferences()
        self._closing = True
        self.cancel_event.set()
        self._finish_close()

    def _finish_close(self):
        if self.busy:
            self.root.after(100, self._finish_close)
        else:
            self._preview_dir.cleanup()
            self.root.destroy()

    def _load_formula_fonts(self):
        # 沿用与正文字体相同的注册表; 默认选中 WenKai（符号最全，公式最稳）
        keys = list(self.style_keys)
        labels = [FORMULA_FONT_LABELS.get(k, k) + (' · 待下载' if not font_manager.installed(k) else '') for k in keys]
        self.fmfont_combo["values"] = labels
        if labels:
            default = "WenKai" if "WenKai" in keys else keys[0]
            self.fmfont_combo.current(keys.index(default))

    # --------------------------------------------------------------- 事件
    def _on_drop(self, event):
        if self.busy:
            return
        paths = self.root.tk.splitlist(event.data)
        mds = [p for p in paths if p.lower().endswith((".md", ".markdown", ".txt", ".docx"))]
        if any(p.lower().endswith('.doc') for p in paths):
            messagebox.showinfo("旧版 Word 文档", "请先用 Word 或 WPS 将 .doc 另存为 .docx。")
        if not mds:
            messagebox.showwarning("提示", "请拖入 .docx / .md / .markdown / .txt 文件")
            return
        self.files = mds
        self._file_summary()
        self._preview_one()

    def _choose_files(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="选择要转写的文档",
            filetypes=[("支持的文档", "*.docx *.md *.markdown *.txt"),
                       ("Word 文档", "*.docx"), ("Markdown", "*.md *.markdown"),
                       ("文本", "*.txt")])
        if paths:
            self.files = list(paths)
            self._file_summary()
            self._preview_one()

    def _file_summary(self):
        self.files = list(dict.fromkeys(os.path.abspath(p) for p in self.files))
        self._approved_snapshot = None
        self.retry_btn.configure(state='disabled')
        self.jobs = [dict(id=str(i), path=path, status='待确认', paths=[], notices=[], error='')
                     for i, path in enumerate(self.files)]
        self.job_tree.delete(*self.job_tree.get_children())
        for job in self.jobs:
            self.job_tree.insert('', 'end', iid=job['id'], values=(os.path.basename(job['path']), job['status']))
        name = os.path.basename(self.files[0])
        if len(name) > 26:
            name = name[:23] + '…'
        self.drop.configure(text=f"已选 {len(self.files)} 份文档 · {name}", fg=ACCENT)

    def _choose_out(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.out_var.set(d)

    def _open_out(self):
        completed = [j for j in self.jobs if j.get('paths')]
        selection = self.job_tree.selection()
        selected = next((j for j in completed if selection and j['id'] == selection[0]), None)
        if selected or completed:
            directory = os.path.dirname((selected or completed[0])['paths'][0])
            if os.path.isdir(directory):
                os.startfile(directory)
                return
        d = self.out_var.get().strip()
        if not d and self.files:
            d = os.path.join(os.path.dirname(os.path.abspath(self.files[0])), "手写体")
        if d and os.path.isdir(d):
            try:
                os.startfile(d)
            except Exception:
                pass
        else:
            messagebox.showinfo("提示", "还没有输出目录")

    # --------------------------------------------------------------- 转换
    def _parameters(self):
        return dict(font=self.style_keys[self.font_combo.current()],
                    font_size=int(self.size_var.get()), ruled=self.ruled_var.get(),
                    line_spacing_ratio=float(self.line_var.get()),
                    word_spacing=float(self.word_var.get()), jitter=float(self.jitter_var.get()),
                    glyph_variation=float(self.glyph_variation_var.get()),
                    formula=bool(self.formula_var.get()),
                    formula_font=os.fspath(font_manager.font_path(self.style_keys[self.fmfont_combo.current()])))

    def _snapshot(self):
        stats = []
        for path in self.files:
            try:
                stat = os.stat(path)
                stats.append((path, stat.st_mtime_ns, stat.st_size))
            except OSError:
                stats.append((path, None))
        return repr((stats, self._parameters(), self.out_var.get(), self.export_var.get()))

    def _preview_one(self):
        if self.busy:
            return
        if not self.files:
            self._choose_files()
            return
        for key in (self.style_keys[self.font_combo.current()], self.style_keys[self.fmfont_combo.current()]):
            if not font_manager.installed(key):
                self.status.configure(text=f'{FONT_LABELS[key]} 尚未安装，请在字体管理器下载。')
                self._font_manager(key)
                return
        self.busy = True
        self.notices = []
        self.cancel_event.clear()
        self.cancel_btn.configure(state='normal')
        self._approved_snapshot = None
        self.go_btn.configure(state='disabled')
        self.preview_btn.configure(state='disabled')
        self.status.configure(text='只排版第一页，正在预览…')
        self.output_paths = []
        self.preview_index = 0
        self._update_navigation()
        self.preview.configure(image='', text='正在快速排版第一页…')
        params, snapshot = self._parameters(), self._snapshot()
        selection = self.job_tree.selection()
        job = next((j for j in self.jobs if selection and j['id'] == selection[0]), self.jobs[0])
        self._preview_jobid = job['id']
        threading.Thread(target=self._preview_worker, args=(job['path'], params, snapshot), daemon=True).start()

    def _font_manager(self, selected=None):
        if hasattr(self, 'font_window') and self.font_window.winfo_exists():
            if self.busy:
                self.font_window.lift()
                return
            self.font_window.destroy()
        window = tk.Toplevel(self.root); window.title('字体管理 · 按需下载')
        window.geometry('720x460'); window.configure(bg=CARD)
        self.font_window = window
        catalog = font_manager.catalog(); keys = list(catalog)
        choices = tk.Listbox(window, width=30, exportselection=False, bd=0,
                             selectbackground='#d9e9df', selectforeground=INK)
        choices.pack(side='left', fill='y', padx=12, pady=16)
        for key in keys:
            choices.insert('end', catalog[key]['label'] + (' ✓' if font_manager.installed(key) else ''))
        info = tk.Frame(window, bg=CARD, padx=16); info.pack(side='left', fill='both', expand=True)
        name = ttk.Label(info, font=('Microsoft YaHei UI', 12, 'bold')); name.pack(anchor='w', pady=(24, 10))
        sample = tk.Label(info, bg=CARD); sample.pack(fill='x', pady=10)
        self.font_info = ttk.Label(info, wraplength=380, justify='left'); self.font_info.pack(anchor='w', pady=10)
        current = [selected or keys[0]]
        def select(event=None):
            index = choices.curselection()
            if not index:
                return
            key = current[0] = keys[index[0]]; item = catalog[key]
            name.configure(text=item['label'])
            with Image.open(os.path.join(hw.FONT_DIR, item['sample'])) as image:
                preview = image.copy(); preview.thumbnail((380, 85))
            sample.image = ImageTk.PhotoImage(preview); sample.configure(image=sample.image)
            state = '已安装，可离线使用' if font_manager.installed(key) else '尚未安装'
            self.font_info.configure(text=f"{state}\n字体大小：{item['size']/1024/1024:.1f} MB\n授权：SIL Open Font License 1.1\n来源：{item['source']}")
        choices.bind('<<ListboxSelect>>', select)
        ttk.Button(info, text='查看官方来源', command=lambda: webbrowser.open(catalog[current[0]]['source'])).pack(fill='x', pady=4)
        ttk.Button(info, text='查看授权', command=lambda: webbrowser.open(catalog[current[0]]['license_url'])).pack(fill='x', pady=4)
        ttk.Button(info, text='下载并安装所选字体', style='Primary.TButton',
                   command=lambda: self._download_font(current[0])).pack(fill='x', pady=8)
        choices.selection_set(keys.index(current[0])); select()

    def _download_font(self, key):
        if self.busy:
            self.font_info.configure(text='请等待当前任务结束。'); return
        if font_manager.installed(key):
            self.font_info.configure(text='字体已安装，无需重新下载。'); return
        self.busy = True; self.cancel_event.clear(); self.cancel_btn.configure(state='normal')
        self.font_info.configure(text='正在下载，可用主窗口取消按钮停止…')
        def work():
            try:
                font_manager.install_font(key, cancel=self.cancel_event.is_set,
                    progress=lambda n: self.q.put(('font_progress', n)))
                self.q.put(('font_done', key, None))
            except Exception as exc:
                self.q.put(('font_done', key, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _preview_worker(self, path, params, snapshot):
        try:
            with warnings.catch_warnings(record=True) as notices:
                warnings.simplefilter('always', UserWarning)
                pages, _ = hw.render_markdown(hw.read_input(path, cancel=self.cancel_event.is_set), page_limit=1,
                                              cancel=self.cancel_event.is_set, **params)
            for note in notices:
                self.q.put(('notice', str(note.message)))
            target = os.path.join(self._preview_dir.name, 'preview.png')
            pages[0].save(target)
            self.q.put(('preview_done', target, snapshot))
        except Exception as exc:
            self.q.put(('preview_error', str(exc)))

    def _start(self, retry=False):
        if self.busy:
            return
        if not self.files:
            self._choose_files()
            return
        if self._approved_snapshot != self._snapshot():
            self._preview_one()
            return
        self.busy = True
        self.cancel_event.clear()
        self.cancel_btn.configure(state='normal')
        self.preview_btn.configure(state='disabled')
        self.retry_btn.configure(state='disabled')
        self.notices = []
        self.go_btn.configure(state="disabled")
        self.prog.configure(value=0, maximum=len(self.files))
        self.status.configure(text="正在转换…")
        params = dict(self._parameters(), outdir=self.out_var.get().strip() or None,
                      export_format='both' if self.export_var.get() == 'PNG + PDF' else 'png')
        jobs = [job.copy() for job in self.jobs if not retry or job['status'] == '失败']
        self.prog.configure(maximum=max(1, len(jobs)))
        self._batch_completed = 0
        threading.Thread(target=self._worker, args=(jobs, params),
                         daemon=True).start()

    def _worker(self, jobs, params):
        results = run_batch(jobs, params, self.cancel_event.is_set,
                            lambda kind, value: self.q.put((kind, value)))
        self.q.put(('batch_done', results))

    def _retry_failed(self):
        if not self.busy and any(job['status'] == '失败' for job in self.jobs):
            self._start(retry=True)

    def _job_detail(self, event=None):
        selection = self.job_tree.selection()
        if not selection:
            return
        job = next(j for j in self.jobs if j['id'] == selection[0])
        if job.get('paths') and not self.busy:
            self.output_paths = job['paths']; self.preview_index = 0
            self._show_preview(self.output_paths[0]); self._update_navigation()
        details = '\n'.join([job.get('error', ''), *job.get('notices', [])]).strip()
        if details:
            window = tk.Toplevel(self.root); window.title(os.path.basename(job['path']) + ' · 问题清单')
            text = tk.Text(window, wrap='word', width=85, height=22)
            bar = ttk.Scrollbar(window, command=text.yview); bar.pack(side='right', fill='y')
            text.configure(yscrollcommand=bar.set); text.pack(fill='both', expand=True)
            text.insert('1.0', details); text.configure(state='disabled')

    def _poll(self):
        """主线程: 定期取出后台消息并刷新界面。"""
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status.configure(text=msg[1])
                elif kind == "prog":
                    self.prog.configure(value=msg[1])
                elif kind == "error":
                    messagebox.showerror("转换失败", msg[1])
                elif kind == "notice":
                    if msg[1] not in self.notices:
                        self.notices.append(msg[1])
                elif kind == 'preview_done':
                    self.busy = False
                    self.cancel_btn.configure(state='disabled')
                    self.preview_btn.configure(state='normal')
                    self.output_paths = [msg[1]]
                    self.preview_index = 0
                    self._update_navigation()
                    self.page_label.configure(text='预览 · 第 1 页（全文未排版）')
                    self._show_preview(msg[1])
                    if msg[2] == self._snapshot():
                        self._approved_snapshot = msg[2]
                        self.go_btn.configure(state='normal')
                        self.status.configure(text='第一页预览完成。满意后点击「确认生成全文」。' +
                                              (f' 有 {len(self.notices)} 项内容问题，双击文件查看。' if self.notices else ''))
                        job = next(j for j in self.jobs if j['id'] == self._preview_jobid)
                        job['notices'] = self.notices.copy()
                    else:
                        self.status.configure(text='预览期间设置已改变，请重新预览。')
                elif kind == 'preview_error':
                    self.busy = False
                    self.cancel_btn.configure(state='disabled')
                    self.preview_btn.configure(state='normal')
                    self.status.configure(text='预览未完成：' + msg[1] + '；可选择队列中的其他文件，再点快速预览。')
                elif kind == 'job':
                    job = msg[1]
                    index = next(i for i, j in enumerate(self.jobs) if j['id'] == job['id'])
                    self.jobs[index] = job
                    label = job['status'] + (f" · {len(job.get('notices', []))} 项提示" if job.get('notices') else '')
                    self.job_tree.item(job['id'], values=(os.path.basename(job['path']), label))
                    if job['status'] != '转换中':
                        self._batch_completed += 1
                        self.prog.configure(value=self._batch_completed)
                elif kind == 'page':
                    self.job_tree.set(msg[1][0], 'status', f'排版中 · {msg[1][1]} 页')
                elif kind == 'batch_done':
                    self.notices = [n for j in msg[1] for n in j.get('notices', [])]
                    paths = [p for j in msg[1] for p in j.get('paths', [])]
                    self._done(paths, all(j['status'] == '完成' for j in msg[1]))
                    counts = {s: sum(j['status'] == s for j in msg[1]) for s in ('完成', '失败', '已取消')}
                    self.status.configure(text=' · '.join(f'{s} {n} 份' for s, n in counts.items()) + '；双击文件查看问题清单。')
                elif kind == 'font_progress':
                    if self.font_window.winfo_exists():
                        self.font_info.configure(text=f'已下载 {msg[1]/1024/1024:.1f} MB…')
                elif kind == 'font_done':
                    self.busy = False; self.cancel_btn.configure(state='disabled')
                    text = '字体安装完成，请重新预览。' if msg[2] is None else '字体下载未完成：' + msg[2]
                    if self.font_window.winfo_exists():
                        self.font_info.configure(text=text)
                    self.status.configure(text=text)
                    current = self.font_combo.current(); formula = self.fmfont_combo.current()
                    self._load_fonts(); self._load_formula_fonts()
                    self.font_combo.current(current); self.fmfont_combo.current(formula)
                elif kind == "done":
                    self._done(msg[1], msg[2])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _done(self, paths, ok):
        self.busy = False
        self.go_btn.configure(state='normal' if self._approved_snapshot == self._snapshot() else 'disabled')
        self.preview_btn.configure(state='normal')
        self.cancel_btn.configure(state='disabled')
        self.retry_btn.configure(state='normal' if any(j['status'] == '失败' for j in self.jobs) else 'disabled')
        self.output_paths = list(paths)
        self.preview_index = 0
        self._update_navigation()
        if paths:
            prefix = "完成" if ok else "部分完成"
            note = '；'.join(self.notices)
            self.status.configure(text=f"{prefix}：共生成 {len(paths)} 页" + (f"\n提示：{note}" if note else ''))
            self._show_preview(paths[0])
        else:
            self.status.configure(text="未生成文件，请检查输入文档")
            self.preview.configure(image='', text="暂无可预览页面")
            self.preview_img = None

    def _update_navigation(self):
        count = len(self.output_paths)
        self.page_label.configure(text=f"{self.preview_index + 1} / {count}" if count else "尚无页面")
        self.prev_btn.configure(state="normal" if self.preview_index > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.preview_index + 1 < count else "disabled")

    def _turn_page(self, offset):
        index = self.preview_index + offset
        if 0 <= index < len(self.output_paths):
            self.preview_index = index
            self._show_preview(self.output_paths[index])
            self._update_navigation()

    def _resize_preview(self, event):
        if hasattr(self, '_preview_resize_id'):
            self.root.after_cancel(self._preview_resize_id)
        self._preview_resize_id = self.root.after(100, self._refresh_preview)

    def _refresh_preview(self):
        if self.output_paths:
            self._show_preview(self.output_paths[self.preview_index])

    def _show_preview(self, path):
        if not Image:
            return
        try:
            with Image.open(path) as source:
                img = source.copy()
            img.thumbnail((max(1, self.preview.winfo_width() - 24),
                           max(1, self.preview.winfo_height() - 24)))
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview.configure(image=self.preview_img, text="")
        except Exception:
            pass


def main():
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = TkinterDnD.Tk() if DND_OK else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
