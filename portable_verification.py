"""Offline verification executed by the distributed interpreter, not host Python."""
import json
import os
from pathlib import Path
import socket
import sys
import warnings


def verify(base,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    base=Path(base).resolve()
    network=[]
    def audit(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.bind'}:
            network.append(event);raise RuntimeError('Offline verification blocks network')
    sys.addaudithook(audit)
    assert Path(sys.executable).resolve().is_relative_to(base/'runtime')
    assert sys.flags.isolated and sys.flags.no_user_site
    for item in sys.path:
        if item:assert Path(item).resolve().is_relative_to(base), 'External Python search path'
    import handwriting as hw
    import font_manager
    from app_settings import settings_path
    from managed_output import generate_document
    from preview_cache import PreviewCache
    from PIL import Image,ImageChops
    state=Path(os.environ['MOJIAN_STATE_DIR']).resolve()
    assert settings_path().resolve().is_relative_to(state)
    assert font_manager.cache_directory().resolve().is_relative_to(state)
    assert Path(hw.FALLBACK).resolve().is_relative_to(base/'fonts')
    params=dict(jitter=.1,glyph_variation=.7)
    sample=base/'examples'/'regression'/'参数对照.md'
    with warnings.catch_warnings(record=True):
        png=generate_document(sample,output/'png',**params)
        pdf=generate_document(sample,output/'pdf',export_format='pdf',preview_root=output/'pdf-preview',**params)
        cache=PreviewCache(output/'preview')
        first,_=cache.get(sample,params,1)
        with Image.open(first['paths'][0]) as a,Image.open(png[0]) as b:
            assert ImageChops.difference(a,b).getbbox() is None
        # Relative local images in a newly created source, outside the app CWD.
        source=output/'inputs';(source/'assets').mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(160,60),'#c43232').save(source/'assets'/'local.png')
        document=source/'relative.md';document.write_text('# 相对路径\n\n![离线图片](assets/local.png)',encoding='utf-8')
        local=generate_document(document,output/'local-image',**params)
        assert not any(i['severity']=='错误' for i in local.issues)
        with Image.open(local[0]) as image:
            assert any(r>150 and g<80 and b<80 for r,g,b in image.getdata()), 'Local image missing'
        comprehensive=base/'examples'/'regression'/'综合回归.md'
        full_png=generate_document(comprehensive,output/'comprehensive-png',**params)
        full_pdf=generate_document(comprehensive,output/'comprehensive-pdf',export_format='pdf',**params)
        assert len(full_png)==full_pdf.page_count
        errors=[item for item in full_png.issues if item['severity']=='错误']
        assert len(errors)==3 and all('E0' in item['section'] for item in errors), 'Unexpected error in normal sample'
    # Exercise actual bundled Tcl/Tk + drag-and-drop + application shutdown.
    import gui
    root=gui.TkinterDnD.Tk() if gui.DND_OK else __import__('tkinter').Tk()
    root.withdraw();app=gui.App(root,settings_file=state/'gui-verification.json')
    temporary=Path(app._preview_dir.name)
    root.after(300,app._close);root.mainloop()
    assert not temporary.exists(), 'Preview temporary directory not cleaned'
    assert not network, 'Unexpected network attempt'
    modules=[]
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name and Path(name).exists():
            resolved=Path(name).resolve()
            assert resolved.is_relative_to(base), 'External module imported'
            modules.append(resolved.relative_to(base).as_posix())
    report=dict(environment='same-host isolated Windows process; not a clean VM',python=sys.version.split()[0],
                isolated=True,network_attempts=len(network),user_site=False,external_modules=False,
                state_isolated=True,bundled_fonts=True,relative_image=True,
                png_pages=len(png),pdf_pages=pdf.page_count,preview_matches=True,
                comprehensive_pages=len(full_png),expected_errors=len(errors),
                tk_gui=True,preview_cleanup=True,modules_checked=len(modules))
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
