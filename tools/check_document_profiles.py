"""Actually convert two synthetic documents through GUI profile resolution."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import warnings
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gui
from batch_tasks import run_batch


def check(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    (output/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(output/'tmp')
    root=gui.TkinterDnD.Tk() if gui.DND_OK else __import__('tkinter').Tk();root.withdraw()
    app=gui.App(root,settings_file=output/'app-state'/'settings.json')
    source=Path(gui.HERE)/'examples'/'regression'/'参数对照.md'
    files=[]
    try:
        for name,size,export in [('one',32,'PDF 文件'),('two',48,'PNG 图片')]:
            path=output/(name+'.md');path.write_bytes(source.read_bytes());files.append(str(path))
            app.document_settings.save(path,dict(font='WenKai',formula_font='WenKai',font_size=size,export_format=export))
        app.files=files;app._file_summary();root.update()
        jobs=[];resolved=[]
        for job in app.jobs:
            params,export,notes=app._job_parameters(job)
            jobs.append(dict(job,params=dict(params,export_format=export),parameter_notes=notes))
            resolved.append((params['font_size'],export))
        assert resolved==[(32,'pdf'),(48,'png')]
        with warnings.catch_warnings(record=True):
            result=run_batch(jobs,dict(outdir=output/'results',preview_root=output/'preview'),lambda:False,lambda *args:None)
        assert all(item['status']=='完成' for item in result)
        assert result[0]['paths'][0].endswith('.pdf') and result[1]['paths'][0].endswith('.png')
        report=dict(resolved=[dict(document=Path(path).name,font_size=size,export_format=export) for path,(size,export) in zip(files,resolved)],
                    completed=True,global_font_size=app._global_preferences['font_size'],
                    pages=[item['page_count'] for item in result])
        (output/'profiles-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:root.destroy();app._preview_dir.cleanup()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='output/profile-verification');args=parser.parse_args();check(args.output)
