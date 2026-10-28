"""Conservative context packing. Large rewrites use exact visible snippet edits."""
import math


def estimate_tokens(text):
    # Deliberately conservative for source, Unicode and JSON escapes; not a tokenizer.
    return math.ceil(len(text.encode('utf-8'))/2)+16


def fit_text(text,budget,from_end=False):
    if budget<=16:return ''
    if estimate_tokens(text)<=budget:return text
    raw=text.encode('utf-8');raw=raw[-(budget-16)*2:] if from_end else raw[:(budget-16)*2]
    return raw.decode('utf-8','ignore')


def excerpt(code,budget,focus=0):
    if estimate_tokens(code)<=budget:return code,{'included_lines':[[1,len(code.splitlines())]],'omitted':False,'characters':len(code)}
    lines=code.splitlines(True);focus=max(0,min(len(code),focus));line=code[:focus].count('\n')
    first=max(0,line-12);last=min(len(lines),line+18)
    while last>first+1 and estimate_tokens(''.join(lines[first:last]))>budget:
        if line-first>last-line:first+=1
        else:last-=1
    value=''.join(lines[first:last]);value=fit_text(value,budget)
    return value,{'included_lines':[[first+1,last]],'omitted':True,'characters':len(code)}


def snippet_edits(code,visible,edits):
    if not isinstance(edits,list) or not 1<=len(edits)<=6:raise ValueError('The model must return one to six exact snippet edits.')
    changes=[]
    for edit in edits:
        if not isinstance(edit,dict) or not isinstance(edit.get('old'),str) or not isinstance(edit.get('new'),str):raise ValueError('Invalid snippet edit.')
        old,new=edit['old'],edit['new']
        if len(old)<8 or old not in visible or code.count(old)!=1:raise ValueError('Snippet edit is ambiguous or outside the supplied context. No source change was accepted.')
        start=code.index(old);changes.append((start,start+len(old),new))
    changes.sort()
    if any(a[1]>b[0] for a,b in zip(changes,changes[1:])):raise ValueError('Snippet edits overlap.')
    for start,end,new in reversed(changes):code=code[:start]+new+code[end:]
    return code
