"""Explicit figure captions and keep groups, measured once on transparent paper."""
import copy
import random
import warnings
from PIL import Image, ImageDraw


def structure_blocks(blocks):
    folded=[]
    for block in blocks:
        if block[0]=='caption':
            index=next((i for i in range(len(folded)-1,-1,-1) if folded[i][0] not in {'source','location','diagnostic'}),None)
            if index is not None and folded[index][0] in {'image','diagram','plot'}:
                figure=folded[index]
                if figure[0]=='image': figure=(figure[0],figure[1],'')
                tail=folded[index+1:]
                folded[index:]=[('keepgroup',[figure,*tail,block])]
            else:
                folded.extend([('diagnostic','警告','图注','图注前没有相邻图形，已作为独立图注显示'),block])
        else: folded.append(block)
    stack=[[]]
    for block in folded:
        if block[0]=='keepstart':
            if len(stack)>8:
                stack[-1].append(('diagnostic','错误','同页组合','组合嵌套超过八层，保留后续内容'));continue
            stack.append([])
        elif block[0]=='keepend':
            if len(stack)==1: stack[0].append(('diagnostic','错误','同页组合','多余的 keep-end，已忽略标记'))
            else:
                group=stack.pop();stack[-1].append(('keepgroup',group))
        else: stack[-1].append(block)
    while len(stack)>1:
        group=stack.pop()
        stack[-1].extend([('diagnostic','错误','同页组合','keep-start 未闭合，保留组合内容'),('keepgroup',group)])
    result=stack[0]
    for index in range(len(result)-1,-1,-1):
        if index>=len(result) or result[index][0]!='keepnext': continue
        end=index+1;count=0
        while end<len(result) and count<2:
            if result[end][0] not in {'source','location','diagnostic'}: count+=1
            end+=1
        payload=result[index+1:end]
        if count<2: payload.insert(0,('diagnostic','警告','keep-next','后续不足两块，已保留可用内容'))
        result[index:end]=[('keepgroup',payload)]
    return result


def draw_group(renderer, blocks, formula):
    def has_break(children):
        return any(block[0]=='pagebreak' or (block[0]=='keepgroup' and has_break(block[1])) for block in children)
    if not getattr(renderer,'_group_probe',False) and has_break(blocks):
        renderer.issue('警告','同页组合','组合包含手动分页，手动分页优先；已按原顺序逐块分页')
        for block in blocks:renderer.draw_block(block,formula)
        return
    if getattr(renderer,'_group_probe',False):
        for block in blocks: renderer.draw_block(block,formula)
        return
    probe=copy.copy(renderer)
    probe._group_probe=True
    for name in ('rand','shape_rand'):
        value=random.Random();value.setstate(getattr(renderer,name).getstate());setattr(probe,name,value)
    probe.pages=[];probe.page_sink=None;probe.page_progress=None;probe.page_limit=1
    probe.page_count=1;probe._flushed_page=0;probe.y=probe.top
    probe.page=Image.new('RGBA',(probe.w,probe.h));probe.draw=ImageDraw.Draw(probe.page)
    probe.occupied={};probe.block_map=[];probe.issues=[];probe.issue_sink=None
    probe._pending_break=False
    if hasattr(renderer,'_missing_glyphs'): probe._missing_glyphs=set(renderer._missing_glyphs)
    overflow=False
    with warnings.catch_warnings(record=True):
        try:
            for block in blocks: probe.draw_block(block,formula)
        except renderer.PageLimitReached:
            overflow=True
    height=probe.y-probe.top
    if not overflow and probe.page_count==1 and height<=renderer.h-renderer.top-renderer.bottom:
        renderer._ensure(height)
        offset=round(renderer.y-renderer.top)
        tile=probe.page.crop((0,renderer.top,renderer.w,round(probe.y)))
        renderer.page.paste(tile,(0,round(renderer.y)),tile)
        for box in probe.occupied.get(1,[]):
            l,t,r,b=box;renderer.record_region('同页组合',(l,t+offset,r,b+offset))
        for item in probe.issues:
            old=renderer.source_line,renderer.section
            renderer.source_line,renderer.section=item.line,item.section
            renderer.issue(item.severity,item.object,item.reason)
            renderer.source_line,renderer.section=old
        for block in probe.block_map:
            renderer.block_map.append(dict(block,page=renderer.page_count,end_page=renderer.page_count,y=block['y']+offset,bottom=block['bottom']+offset))
        renderer.y+=height
        renderer.rand.setstate(probe.rand.getstate());renderer.shape_rand.setstate(probe.shape_rand.getstate())
        renderer._writing_slant=probe._writing_slant;renderer._writing_scale=probe._writing_scale
        renderer._pending_break=probe._pending_break
    else:
        renderer.issue('警告','同页组合','组合超过一页或包含手动分页，已按原顺序逐块分页；不反复移页、不裁切整组')
        for block in blocks: renderer.draw_block(block,formula)
