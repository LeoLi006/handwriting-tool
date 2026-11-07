"""Debounced, cache-backed comparison of one fixed original short document."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from preview_cache import PreviewCache, fingerprint

SAMPLE=Path(__file__).resolve().parent/'examples'/'regression'/'参数对照.md'


def comparable_params(params):
    return dict(params,seed=20231029,dpi=150)


def differences(before,after):
    return {key:(before.get(key),after.get(key)) for key in sorted(set(before)|set(after)) if before.get(key)!=after.get(key)}


class ComparisonWindow:
    def __init__(self,app):
        self.app=app;self.busy=False;self.cancel=threading.Event();self.q=queue.Queue()
        self.baseline=comparable_params(app._parameters());self.revision=0;self.timer=None;self.closed=False
        if not hasattr(app,'comparison_cache'):
            app.comparison_cache=PreviewCache(Path(app._preview_dir.name)/'comparison',capacity=4)
        self.cache=app.comparison_cache
        self.window=tk.Toplevel(app.root);self.window.title('参数调整前后对照 · 固定内容与随机种子')
        self.window.geometry('1200x820');self.window.protocol('WM_DELETE_WINDOW',self.close)
        bar=ttk.Frame(self.window);bar.pack(fill='x',padx=12,pady=8)
        ttk.Button(bar,text='当前设为新基准',command=self.set_baseline).pack(side='left')
        ttk.Button(bar,text='刷新短示例',command=self.schedule).pack(side='left',padx=8)
        ttk.Label(bar,text='共同页码').pack(side='left');self.page=tk.StringVar(value='1')
        ttk.Spinbox(bar,from_=1,to=20,textvariable=self.page,width=4).pack(side='left',padx=4)
        ttk.Label(bar,text='共同缩放').pack(side='left');self.zoom=tk.StringVar(value='40%')
        ttk.Combobox(bar,textvariable=self.zoom,values=['25%','40%','60%','100%'],width=5,state='readonly').pack(side='left',padx=4)
        self.changed=ttk.Label(self.window,text='',wraplength=1140);self.changed.pack(fill='x',padx=12,pady=4)
        self.status=ttk.Label(self.window,text='短示例正在准备；正式文档不会随滑块自动重做。');self.status.pack(fill='x',padx=12,pady=4)
        panels=ttk.Frame(self.window);panels.pack(fill='both',expand=True,padx=12,pady=8)
        self.canvases=[];self.photos=[];self.paths=[None,None]
        for col,title in enumerate(('调整前：固定基准','调整后：当前参数')):
            frame=ttk.Frame(panels);frame.grid(row=0,column=col,sticky='nsew',padx=4)
            panels.columnconfigure(col,weight=1,uniform='side');panels.rowconfigure(0,weight=1)
            ttk.Label(frame,text=title).pack()
            xbar=ttk.Scrollbar(frame,orient='horizontal');xbar.pack(side='bottom',fill='x')
            ybar=ttk.Scrollbar(frame);ybar.pack(side='right',fill='y')
            canvas=tk.Canvas(frame,bg='#e9eeeb',highlightthickness=0,xscrollcommand=xbar.set,yscrollcommand=ybar.set)
            canvas.pack(fill='both',expand=True);xbar.configure(command=canvas.xview);ybar.configure(command=canvas.yview)
            self.canvases.append(canvas)
        self.page.trace_add('write',lambda *args:self.schedule())
        self.zoom.trace_add('write',lambda *args:self.redraw())
        app.ui_scaling.register(self.window)
        self.poll_id=self.window.after(80,self.poll);self.monitor_id=self.window.after(1000,self.monitor)
        self.schedule()

    def set_baseline(self):
        self.baseline=comparable_params(self.app._parameters());self.schedule()

    def describe_changes(self):
        diff=differences(self.baseline,comparable_params(self.app._parameters()))
        def label(value):
            if isinstance(value,str) and ('\\' in value or '/' in value):return Path(value).name
            return str(value)
        self.changed.configure(text='变化参数：'+('；'.join(f'{k}: {label(a)} → {label(b)}' for k,(a,b) in diff.items()) or '无；两侧参数相同'))

    def schedule(self):
        if self.closed:return
        self.revision+=1;self.describe_changes();self.paths=[None,None];self.redraw()
        self.status.configure(text='等待滑块停止 500 ms 后更新；相同内容、种子、页码和缩放。')
        if self.timer:self.window.after_cancel(self.timer)
        self.timer=self.window.after(500,self.start)

    def signature(self):
        params=comparable_params(self.app._parameters())
        return (fingerprint(SAMPLE,self.baseline),fingerprint(SAMPLE,params),self.page.get())

    def monitor(self):
        if self.closed:return
        # Checking file stats is cheap; content hashes are evaluated at render.
        files={SAMPLE,Path(__import__('handwriting').FALLBACK)}
        for params in (self.baseline,comparable_params(self.app._parameters())):
            for key in ('font','formula_font'):
                value=params.get(key)
                if value and Path(value).is_file():files.add(Path(value))
                elif key=='font' and value:
                    import font_manager
                    try:files.add(Path(font_manager.font_path(value)))
                    except KeyError:pass
        signature=[]
        for path in sorted(files):
            try:s=path.stat();signature.append((str(path),s.st_mtime_ns,s.st_size))
            except OSError:signature.append((str(path),None))
        if hasattr(self,'resource_stats') and self.resource_stats!=signature:self.schedule()
        self.resource_stats=signature
        self.monitor_id=self.window.after(1000,self.monitor)

    def start(self):
        self.timer=None
        if self.closed:return
        if self.busy or self.app.busy:
            self.timer=self.window.after(150,self.start);return
        try:
            page=int(self.page.get())
            if not 1<=page<=20:raise ValueError()
            signature=self.signature()
        except (ValueError,OSError) as exc:
            self.status.configure(text='示例页码或资源无效：'+str(exc));return
        revision=self.revision;before=dict(self.baseline);after=comparable_params(self.app._parameters())
        self.busy=True;self.status.configure(text='只更新固定短示例…')
        def work():
            try:
                left,hit1=self.cache.get(SAMPLE,before,page,cancel=self.cancel.is_set)
                right,hit2=self.cache.get(SAMPLE,after,page,cancel=self.cancel.is_set)
                self.q.put((revision,signature,page,left,right,hit1 and hit2,None))
            except Exception as exc:self.q.put((revision,signature,page,None,None,False,str(exc)))
            finally:self.busy=False
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if self.closed:return
        try:
            while True:
                rev,signature,page,left,right,cached,error=self.q.get_nowait()
                if rev!=self.revision:continue
                if signature!=self.signature():self.schedule();continue
                if error:self.status.configure(text='短示例未完成：'+error);continue
                self.paths=[entry['paths'][page-1] if len(entry['paths'])>=page else None for entry in (left,right)]
                self.redraw();self.status.configure(text=f'共同第 {page} 页，种子 20231029；'+('已复用缓存。' if cached else '已更新。')+' 某侧没有该页时明确留空，不替换为其他页。')
        except queue.Empty:pass
        except OSError:self.schedule()
        self.poll_id=self.window.after(80,self.poll)

    def redraw(self):
        self.photos=[]
        factor=float(self.zoom.get().rstrip('%'))/100
        for canvas,path in zip(self.canvases,self.paths):
            canvas.delete('all')
            if path:
                try:
                    with Image.open(path) as source:image=source.resize((round(source.width*factor),round(source.height*factor)),Image.Resampling.LANCZOS)
                    photo=ImageTk.PhotoImage(image);self.photos.append(photo)
                    canvas.create_image(0,0,image=photo,anchor='nw');canvas.configure(scrollregion=(0,0,image.width,image.height))
                except OSError:canvas.create_text(20,30,text='缓存已失效，请刷新',anchor='nw')
            else:canvas.create_text(20,30,text='待更新 / 没有该页',anchor='nw')

    def close(self):
        self.closed=True;self.cancel.set()
        for identifier in (self.timer,self.poll_id,self.monitor_id):
            if identifier:self.window.after_cancel(identifier)
        self.window.destroy()
