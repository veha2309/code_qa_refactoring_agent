"""Small, predictable indentation rules for the native editor."""
import io
import re
import tokenize
from collections import Counter


def indent_style(text,language):
    prefixes=[re.match(r'[ \t]*',line).group() for line in text.splitlines()[:300] if line.strip()]
    tabbed=sum(prefix.startswith('\t') for prefix in prefixes)
    spaced=[len(prefix) for prefix in prefixes if prefix and '\t' not in prefix]
    default=2 if language in {'javascript','typescript','tsx','dart'} else 4
    if tabbed>len(spaced):return '\t',4
    if spaced:
        candidates=[width for width in (2,4,8) if all(n%width==0 for n in spaced)]
        if candidates:default=min(min(spaced),max(candidates))
    return ' '*default,default


def code_tail(prefix,language):
    if language=='python':
        last=''
        try:
            for token in tokenize.generate_tokens(io.StringIO(prefix+'\n').readline):
                if token.type not in {tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE,tokenize.INDENT,tokenize.DEDENT,tokenize.ENDMARKER}:
                    last=token.string if token.type!=tokenize.STRING else '<string>'
        except (tokenize.TokenError,IndentationError):pass
        return last
    out=[];quote=None;escaped=False
    for index,char in enumerate(prefix):
        if quote:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char==quote:quote=None
            continue
        if prefix[index:index+2] in {'//','/*'}:break
        if char in {'"',"'",'`'}:quote=char;out.append('s')
        else:out.append(char)
    clean=''.join(out).rstrip();return clean[-1:] if clean else ''
