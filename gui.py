# coding: utf-8
r"""
手写体转换器 - 图形界面
把 .md 文件拖进窗口即可转成手写体 PNG 图片。

运行:
    python 手写体工具/gui.py     (或双击 启动GUI.bat)

依赖: handright, fonttools, pillow, tkinterdnd2, matplotlib
"""

import os
import queue
import sys
import threading
import traceback

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

ACCENT = "#2f6fb3"
BG = "#f5f7fa"

FONT_LABELS = {
    "WenKai": "霞鹜文楷（工整·默认）",
    "MaShanZheng": "马善政墨韵（毛笔楷书）",
    "LongCang": "龙藏体（硬笔行书）",
    "LiuJianMaoCao": "六剑毛笔草（草书）",
    "ZhiMangXing": "志莽行书（行书）",
    "ZCOOLKuaiLe": "站酷快乐体（卡通）",
}
# 公式字体（需要符号齐全，matplotlib mathtext 用它渲染二维公式）
FORMULA_FONT_LABELS = {
    "WenKai": "霞鹜文楷（推荐·符号最全）",
    "MaShanZheng": "马善政墨韵",
    "LongCang": "龙藏体",
    "LiuJianMaoCao": "六剑毛笔草",
    "ZhiMangXing": "志莽行书",
    "ZCOOLKuaiLe": "站酷快乐体",
}


class App:
    def __init__(self, root):
        self.root = root
        self.files = []
        self.preview_img = None
        self.busy = False
        self.q = queue.Queue()      # worker 线程 -> 主线程 的消息队列

        root.title("Markdown → 手写体 转换器")
        root.geometry("920x780")
        root.minsize(820, 560)
        root.configure(bg=BG)

        self._build_style()
        self._build_layout()
        self.root.after(80, self._poll)   # 主线程轮询队列

    # ------------------------------------------------------------------ UI
    def _build_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TLabel", background=BG, font=("Microsoft YaHei UI", 10))
        st.configure("Head.TLabel", font=("Microsoft YaHei UI", 12, "bold"),
                     foreground=ACCENT, background=BG)
        st.configure("TButton", font=("Microsoft YaHei UI", 10))
        st.configure("Go.TButton", font=("Microsoft YaHei UI", 11, "bold"))
        st.configure("TCheckbutton", background=BG)

    def _build_layout(self):
        panel = tk.Frame(self.root, bg=BG, width=340)
        panel.pack(side="left", fill="y", padx=(14, 6), pady=14)
        panel.pack_propagate(False)
        scroll = tk.Canvas(panel, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(panel, orient="vertical", command=scroll.yview)
        bar.pack(side="right", fill="y")
        scroll.pack(side="left", fill="both", expand=True)
        scroll.configure(yscrollcommand=bar.set)
        left = tk.Frame(scroll, bg=BG)
        window = scroll.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>", lambda e: scroll.itemconfigure(window, width=e.width))

        right = tk.Frame(self.root, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(6, 14), pady=14)

        # ---- 左：参数
        ttk.Label(left, text="① 选择字体", style="Head.TLabel").pack(anchor="w")
        self.font_var = tk.StringVar()
        self.font_combo = ttk.Combobox(left, textvariable=self.font_var,
                                       state="readonly", values=[])
        self.font_combo.pack(fill="x", pady=(4, 12))
        self._load_fonts()

        ttk.Label(left, text="② 字号", style="Head.TLabel").pack(anchor="w")
        self.size_var = tk.IntVar(value=40)
        self._slider(left, self.size_var, 24, 64, None)

        ttk.Label(left, text="③ 行距（越大越松）", style="Head.TLabel").pack(anchor="w", pady=(10, 0))
        self.line_var = tk.DoubleVar(value=1.4)
        self._slider(left, self.line_var, 0.9, 2.6, None, step=0.05)

        ttk.Label(left, text="④ 字距（像素，负=更挤）", style="Head.TLabel").pack(anchor="w", pady=(10, 0))
        self.word_var = tk.DoubleVar(value=0.0)
        self._slider(left, self.word_var, -10, 16, None, step=1)

        ttk.Label(left, text="⑤ 位置/旋转随机度（0=整齐）",
                  style="Head.TLabel").pack(anchor="w", pady=(10, 0))
        self.jitter_var = tk.DoubleVar(value=1.0)
        self._slider(left, self.jitter_var, 0.0, 2.5, None, step=0.1)

        ttk.Label(left, text="⑥ 字形变化强度（不改变排版位置）",
                  style="Head.TLabel").pack(anchor="w", pady=(10, 0))
        self.glyph_variation_var = tk.DoubleVar(value=1.0)
        self._slider(left, self.glyph_variation_var, 0.0, 1.8, None, step=0.1)

        self.ruled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="横线本背景", variable=self.ruled_var).pack(anchor="w", pady=(12, 4))

        self.formula_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="公式二维渲染（更接近手写公式）",
                        variable=self.formula_var).pack(anchor="w", pady=(2, 4))

        ttk.Label(left, text="⑦ 公式字体", style="Head.TLabel").pack(anchor="w", pady=(4, 0))
        self.formula_font_var = tk.StringVar()
        self.fmfont_combo = ttk.Combobox(left, textvariable=self.formula_font_var,
                                         state="readonly", values=[])
        self.fmfont_combo.pack(fill="x", pady=(4, 6))
        self._load_formula_fonts()

        ttk.Label(left, text="⑧ 输出目录（留空=源文件同级/手写体）",
                  style="Head.TLabel").pack(anchor="w", pady=(8, 0))
        row = tk.Frame(left, bg=BG)
        row.pack(fill="x", pady=(4, 6))
        self.out_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="…", width=3, command=self._choose_out).pack(side="left", padx=(4, 0))

        self.go_btn = ttk.Button(left, text="开始转换", style="Go.TButton",
                                 command=self._start)
        self.go_btn.pack(fill="x", pady=(12, 4))
        ttk.Button(left, text="打开输出目录", command=self._open_out).pack(fill="x")

        self.prog = ttk.Progressbar(left, mode="determinate")
        self.prog.pack(fill="x", pady=(10, 0))

        # ---- 右：拖拽区 + 预览
        ttk.Label(right, text="把 .md 文件拖到这里（可多选）", style="Head.TLabel") \
            .pack(anchor="w")

        self.drop = tk.Label(right, text="⬇\n\n拖拽 .md 文件到此处\n\n或点击选择文件",
                             bg="#ffffff", fg="#8a93a3",
                             font=("Microsoft YaHei UI", 13), justify="center",
                             bd=2, relief="groove")
        self.drop.pack(fill="x", pady=(6, 10), ipady=26)
        self.drop.bind("<Button-1>", lambda e: self._choose_files())

        self.status = ttk.Label(right, text="就绪", style="TLabel")
        self.status.pack(anchor="w")

        self.preview = tk.Label(right, bg="#e8ecf2", text="（预览）", fg="#9aa3b2")
        self.preview.pack(fill="both", expand=True, pady=(8, 0))

        if DND_OK:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
        else:
            self.drop.configure(text="⬇\n\n点击选择 .md 文件\n\n(未安装 tkinterdnd2，暂不支持拖拽)")

    def _slider(self, parent, var, lo, hi, cb, step=None):
        s = tk.Scale(parent, from_=lo, to=hi, orient="horizontal", variable=var,
                     resolution=step if step is not None else 1,
                     bg=BG, highlightthickness=0, bd=0,
                     troughcolor="#d8dee7", activebackground=ACCENT,
                     length=250, command=(lambda e: cb()) if cb else None)
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
        paths = self.root.tk.splitlist(event.data)
        mds = [p for p in paths if p.lower().endswith((".md", ".markdown", ".txt"))]
        if not mds:
            messagebox.showwarning("提示", "请拖入 .md / .markdown / .txt 文件")
            return
        self.files = mds
        self.drop.configure(text=" ".join(os.path.basename(p) for p in mds),
                            fg="#2f6fb3")
        self._start()

    def _choose_files(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="选择 Markdown 文件",
            filetypes=[("Markdown", "*.md *.markdown"), ("文本", "*.txt"), ("所有文件", "*.*")])
        if paths:
            self.files = list(paths)
            self.drop.configure(text=" ".join(os.path.basename(p) for p in self.files),
                                fg="#2f6fb3")
            self._start()

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
        if self.busy or not self.files:
            return
        self.busy = True
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
            formula_font=hw.resolve_font(
                self.style_keys[self.fmfont_combo.current()]),
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
                paths = hw.convert_file(f, **params)
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
                elif kind == "done":
                    self._done(msg[1], msg[2])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _done(self, paths, ok):
        self.busy = False
        self.go_btn.configure(state="normal")
        if ok and paths:
            self.status.configure(text=f"完成：共生成 {len(paths)} 页")
            self._show_preview(paths[0])
        else:
            self.status.configure(text="未生成文件")

    def _show_preview(self, path):
        if not Image:
            return
        try:
            img = Image.open(path)
            img.thumbnail((520, 520))
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview.configure(image=self.preview_img, text="")
        except Exception:
            pass


def main():
    root = TkinterDnD.Tk() if DND_OK else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
