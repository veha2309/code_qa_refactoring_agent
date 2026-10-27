"""Bounded literal search without executing repository code."""
from bisect import bisect_right
from pathlib import Path
import re
from .core import checkpoint,decode_source,MAX_BYTES

TEXT_EXTENSIONS={'.py','.js','.jsx','.mjs','.cjs','.ts','.tsx','.mts','.cts','.java','.cs','.go','.rs','.json','.jsonc','.md','.txt','.toml','.yaml','.yml','.html','.css','.scss','.xml','.gradle','.kt'}
TEXT_EXTENSIONS.add('.dart')

def text_matches(source,query,case=False,limit=2000):
    if not query:return [],False
    result=[];previous=0;units=0
    for match in re.finditer(re.escape(query),source,0 if case else re.IGNORECASE):
        if len(result)>=limit:return result,True
        units+=len(source[previous:match.start()].encode('utf-16-le'))//2
        end=units+len(match.group().encode('utf-16-le'))//2
        result.append((units,end));units=end;previous=match.end()
    return result,False

def search_project(root,paths,query,case=False,buffers=None,cancel=None):
    root=Path(root).resolve();rows=[];scanned=0;skipped=0;budget=32_000_000;limited=False
    if not query:return {'rows':[],'scanned':0,'skipped':0,'limited':False}
    pattern=re.compile(re.escape(query),0 if case else re.IGNORECASE)
    for relative in list(paths)[:10000]:
        checkpoint(cancel);path=root/relative
        if path.suffix.lower() not in TEXT_EXTENSIONS:continue
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root):continue
            if relative in (buffers or {}):source=buffers[relative];size=len(source.encode('utf-8'))
            else:
                size=path.stat().st_size
                if size>MAX_BYTES:skipped+=1;continue
                source=decode_source(path.read_bytes(),path)
            if size>MAX_BYTES:skipped+=1;continue
            budget-=size
            if budget<0:limited=True;break
            scanned+=1;lines=source.splitlines();starts=[0]+[m.end() for m in re.finditer('\n',source)]
            for match in pattern.finditer(source):
                checkpoint(cancel)
                if len(rows)>=500:limited=True;break
                line=bisect_right(starts,match.start())-1
                rows.append({'path':relative,'line':line+1,'column':match.start()-starts[line],'preview':lines[line].strip()[:240] if line<len(lines) else ''})
            if limited:break
        except (OSError,UnicodeError):skipped+=1
    return {'rows':rows,'scanned':scanned,'skipped':skipped,'limited':limited or len(paths)>10000}
