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
    def __init__(self, root):
        self.root = root
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
        tk.Label(header, text="本地转换  ·  A4 PNG", bg=BG, fg=ACCENT).pack(side="right", pady=(10, 0))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        panel = tk.Frame(body, bg=CARD, width=330)
        panel.pack(side="left", fill="y", padx=(0, 18))
        panel.pack_propagate(False)
        # Keep the conversion button visible even when the settings need scrolling.
        actions = tk.Frame(panel, bg=CARD)
        actions.pack(side="bottom", fill="x", padx=18, pady=16)
        self.go_btn = ttk.Button(actions, text="开始转换", style="Primary.TButton", command=self._start)
        self.go_btn.pack(fill="x")
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

        section("字体与排版", "选择字迹，调整纸上的疏密")
        self.font_var = tk.StringVar()
        self.font_combo = ttk.Combobox(left, textvariable=self.font_var, state="readonly")
        self.font_combo.pack(fill="x", pady=(0, 6)); self._load_fonts()
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

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        upload = tk.Frame(right, bg=CARD, padx=20, pady=16)
        upload.pack(fill="x")
        self.drop = tk.Label(upload, text="拖入文档，开始转写", bg="#f0f6f2", fg=ACCENT,
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
            self.drop.configure(text="点击选择文档，开始转写")

        preview_card = tk.Frame(right, bg=CARD, padx=16, pady=12)
        preview_card.pack(fill="both", expand=True, pady=(14, 0))
        toolbar = tk.Frame(preview_card, bg=CARD); toolbar.pack(fill="x", pady=(0, 10))
        tk.Label(toolbar, text="纸张预览", bg=CARD, fg=INK,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        ttk.Button(toolbar, text="打开输出目录", command=self._open_out).pack(side="right")
        self.preview = tk.Label(preview_card, bg="#e9eeeb", fg=MUTED,
                                text="预览将在这里显示\n\n选择文档后自动转换", font=("Microsoft YaHei UI", 12))
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
        labels = [FONT_LABELS.get(k, k) for k in self.style_keys]
        self.font_combo["values"] = labels
        if labels:
            default = "WenKai" if "WenKai" in self.style_keys else self.style_keys[0]
            self.font_combo.current(self.style_keys.index(default))

    def _load_formula_fonts(self):
        # 沿用与正文字体相同的注册表; 默认选中 WenKai（符号最全，公式最稳）
        keys = list(self.style_keys)
        labels = [FORMULA_FONT_LABELS.get(k, k) for k in keys]
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
        self._start()

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
            self._start()

    def _file_summary(self):
        name = os.path.basename(self.files[0])
        if len(name) > 26:
            name = name[:23] + '…'
        self.drop.configure(text=f"已选 {len(self.files)} 份文档 · {name}", fg=ACCENT)

    def _choose_out(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.out_var.set(d)

    def _open_out(self):
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
    def _start(self):
        if self.busy:
            return
        if not self.files:
            self._choose_files()
            return
        self.busy = True
        self.notices = []
        self.go_btn.configure(state="disabled")
        self.prog.configure(value=0, maximum=len(self.files))
        self.status.configure(text="正在转换…")
        params = dict(
            font=self.style_keys[self.font_combo.current()],
            font_size=int(self.size_var.get()),
            ruled=self.ruled_var.get(),
            line_spacing_ratio=float(self.line_var.get()),
            word_spacing=float(self.word_var.get()),
            jitter=float(self.jitter_var.get()),
            glyph_variation=float(self.glyph_variation_var.get()),
            formula=bool(self.formula_var.get()),
            formula_font=os.path.join(hw.FONT_DIR, hw.load_registry()[
                self.style_keys[self.fmfont_combo.current()]]),
            outdir=self.out_var.get().strip() or None,
        )
        files = list(self.files)
        threading.Thread(target=self._worker, args=(files, params),
                         daemon=True).start()

    def _worker(self, files, params):
        """后台线程: 只往队列里放消息, 不直接碰 tkinter。"""
        all_paths = []
        try:
            for idx, f in enumerate(files, 1):
                self.q.put(("status", f"转换中 ({idx}/{len(files)})：{os.path.basename(f)}"))
                with warnings.catch_warnings(record=True) as notices:
                    warnings.simplefilter("always", UserWarning)
                    paths = hw.convert_file(f, **params)
                for notice in notices:
                    self.q.put(("notice", str(notice.message)))
                all_paths += paths
                self.q.put(("prog", idx))
        except Exception as e:
            self.q.put(("error", f"{e}\n\n{traceback.format_exc()[-600:]}"))
            self.q.put(("done", all_paths, False))
            return
        self.q.put(("done", all_paths, True))

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
                elif kind == "done":
                    self._done(msg[1], msg[2])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _done(self, paths, ok):
        self.busy = False
        self.go_btn.configure(state="normal")
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
