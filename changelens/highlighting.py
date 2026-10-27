"""Syntax color only: lexers never execute or import project modules."""
from PySide6.QtGui import QColor,QSyntaxHighlighter,QTextCharFormat


class ForeignHighlighter(QSyntaxHighlighter):
    def __init__(self,document,path):
        super().__init__(document)
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound
        try:self.lexer=get_lexer_for_filename(str(path))
        except ClassNotFound:
            from pygments.lexers.special import TextLexer
            self.lexer=TextLexer()

    def highlightBlock(self,text):
        from pygments.token import Keyword,String,Number,Comment,Name
        self.setCurrentBlockState(0)
        if len(text)>12000:return
        start=0
        if self.previousBlockState()==1:
            end=text.find("*/")
            if end<0:self.setFormat(0,len(text),QColor("#7f8a90"));self.setCurrentBlockState(1);return
            start=end+2;self.setFormat(0,start,QColor("#7f8a90"))
        for offset,token,value in self.lexer.get_tokens_unprocessed(text[start:]):
            color=None
            for category,shade in ((Comment,"#7f8a90"),(Keyword,"#c678dd"),(String,"#98c379"),(Number,"#d19a66"),(Name.Function,"#61afef"),(Name.Class,"#e5c07b"),(Name.Builtin,"#56b6c2")):
                if token in category:color=shade;break
            if color:
                fmt=QTextCharFormat();fmt.setForeground(QColor(color));self.setFormat(start+offset,len(value),fmt)
            if token in Comment.Multiline and "/*" in value and "*/" not in value:self.setCurrentBlockState(1)
