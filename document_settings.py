"""Private per-document profiles identified without storing document text/paths."""
import hashlib
import json
import os
from pathlib import Path
import uuid
from app_settings import settings_path, validate

KEYS={'font','formula_font','font_size','line_spacing_ratio','word_spacing','jitter',
      'glyph_variation','formula_variation','table_variation','diagram_variation','ruled','formula','export_format'}


def profile(data):
    result={key:value for key,value in validate(data).items() if key in KEYS}
    if result.get('export_format')=='PNG + PDF':result['export_format']='PDF 文件'
    if result.get('export_format') not in {None,'PNG 图片','PDF 文件'}:result.pop('export_format',None)
    return result


def identity(path):
    path=Path(path).resolve();stat=path.stat()
    digest=lambda value:hashlib.sha256(value).hexdigest()
    birth=getattr(stat,'st_birthtime_ns',stat.st_ctime_ns if os.name=='nt' else 0)
    file_key=digest(f'{stat.st_dev}:{stat.st_ino}:{birth}'.encode()) if stat.st_ino else None
    return dict(path_key=digest(os.path.normcase(str(path)).encode('utf-8')),
                file_key=file_key,content_key=digest(path.read_bytes()))


class DocumentSettings:
    def __init__(self,path=None):
        self.path=Path(path or settings_path().parent/'documents.json')

    def read(self):
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('version') not in {1,2} or not isinstance(data.get('records'),dict):
                raise ValueError('schema')
            return data,''
        except FileNotFoundError:return dict(version=2,records={}),''
        except (OSError,ValueError):return dict(version=2,records={}), '文档设置无效或无法读取，未套用旧配置'

    def write(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        target=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(target,self.path)
        finally:target.unlink(missing_ok=True)

    def match(self,data,current):
        records=data['records']
        exact=[key for key,item in records.items() if isinstance(item,dict) and current['file_key'] and item.get('file_key')==current['file_key']]
        if len(exact)==1:return exact[0],''
        if len(exact)>1:return None,'文档身份对应多份配置，未自动套用'
        legacy=[key for key,item in records.items() if isinstance(item,dict) and not item.get('file_key') and item.get('path_key')==current['path_key'] and item.get('content_key')==current['content_key']]
        if len(legacy)==1:return legacy[0],'旧版配置按路径摘要与内容摘要匹配迁移'
        if len(legacy)>1:return None,'旧版配置存在歧义，未套用'
        if any(isinstance(item,dict) and item.get('path_key')==current['path_key'] for item in records.values()):
            return None,'同一路径的文件身份已变化，未将另一文档的配置套入'
        return None,''

    def load(self,source):
        data,note=self.read()
        if note:return {},note
        current=identity(source);key,note=self.match(data,current)
        if key is None:return {},note
        raw=data['records'][key].get('settings')
        if not isinstance(raw,dict):return {},'文档配置内容无效，未套用'
        clean=profile(raw)
        if not clean:return {},'文档配置没有有效参数，未套用'
        if clean!=raw:note=(note+'；' if note else '')+'无效字段已过滤'
        updated=dict(current,settings=clean)
        changed=data['records'][key]!=updated or data['version']!=2
        data['records'][key]=updated;data['version']=2
        if changed:self.write(data)
        return clean,note

    def save(self,source,settings):
        data,note=self.read()
        if note and self.path.exists():
            raise ValueError(note+'；请先重置无效配置，避免覆盖其他记录')
        current=identity(source);key,_=self.match(data,current)
        if key is None:key=uuid.uuid4().hex
        data['records'][key]=dict(current,settings=profile(settings));data['version']=2
        self.write(data)

    def reset(self,source):
        data,note=self.read()
        if note:
            backup=self.path.with_name(self.path.stem+'.invalid-'+uuid.uuid4().hex+'.json')
            self.path.replace(backup)
            self.write(dict(version=2,records={}))
            return '无效配置已整体备份并重建，备份位于应用配置目录'
        key,note=self.match(data,identity(source))
        if key is not None:
            del data['records'][key];self.write(data)
        return note
