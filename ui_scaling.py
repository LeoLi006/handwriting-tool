"""Resize UI fonts with the window without changing document render settings."""
import math
from tkinter import font as tkfont, ttk


class ResponsiveFonts:
    def __init__(self, root, callback=None):
        self.root, self.callback = root, callback
        self.fonts = {}
        self.scale = 1.0
        self.timer = None
        self.style = ttk.Style(root)
        base = self.managed_font(('Microsoft YaHei UI', 10))
        bold = self.managed_font(('Microsoft YaHei UI', 10, 'bold'))
        root.option_add('*Font', str(base))
        root.option_add('*TCombobox*Listbox.font', str(base))
        for name in ('TLabel', 'TButton', 'TCombobox', 'TEntry', 'TCheckbutton', 'Treeview'):
            self.style.configure(name, font=base)
        self.style.configure('Primary.TButton', font=bold)
        self.style.configure('Treeview.Heading', font=bold)
        self.register(root)
        root.bind('<Configure>', self._configure, add='+')

    def managed_font(self, specification):
        if str(specification) in {str(font) for font in self.fonts.values()}:
            return specification
        actual = tkfont.Font(root=self.root, font=specification).actual()
        key = tuple(actual[name] for name in ('family', 'size', 'weight', 'slant', 'underline', 'overstrike'))
        if key not in self.fonts:
            self.fonts[key] = tkfont.Font(root=self.root, **actual)
        return self.fonts[key]

    def register(self, widget):
        if 'font' in widget.keys():
            specification = widget.cget('font')
            if specification:
                widget.configure(font=self.managed_font(specification))
        for child in widget.winfo_children():
            self.register(child)
        self._apply_fonts()

    def _configure(self, event):
        if event.widget is not self.root:
            return
        if self.timer:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(90, self.resize)

    def _apply_fonts(self):
        for key, font in self.fonts.items():
            original = key[1]
            size = max(8, round(abs(original)*self.scale))
            font.configure(size=size if original > 0 else -size)
        self.style.configure('Treeview', rowheight=max(22, round(25*self.scale)))

    def resize(self):
        self.timer = None
        width, height = self.root.winfo_width(), self.root.winfo_height()
        scale = min(3.0, max(.9, math.sqrt(width/1080 * height/800)))
        if abs(scale-self.scale) < .012:
            return
        self.scale = scale
        self._apply_fonts()
        if self.callback:
            self.callback(scale, width, height)
