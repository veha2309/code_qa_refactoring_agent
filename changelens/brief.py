"""Readable, inert Markdown for model briefs; no link navigation or resources."""
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QTextBrowser
import json


def brief_markdown(answer):
    value=json.loads(answer)
    if not isinstance(value,dict):raise ValueError("The model did not return a focused brief. Try a smaller selection.")
    summary=value.get("summary"); uncertainty=value.get("uncertainty"); checks=value.get("verification")
    if not isinstance(summary,str) or not summary.strip() or not isinstance(uncertainty,str) or not isinstance(checks,list) or not all(isinstance(item,str) for item in checks):
        raise ValueError("The model did not return a valid focused brief. Try again with a smaller selection.")
    def bounded(text,limit):
        words=text.split(); result=" ".join(words[:limit])+("…" if len(words)>limit else "")
        if result.count("**")%2:result+="**"
        if result.count("`")%2:result+="`"
        return result
    return "## What connects\n\n"+bounded(summary,60)+"\n\n## Still uncertain\n\n"+bounded(uncertainty,40)+"\n\n## What to verify\n\n"+"\n".join("- "+bounded(item,25) for item in checks[:3])


class BriefView(QTextBrowser):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("briefView"); self.setOpenLinks(False); self.setOpenExternalLinks(False)
        self.document().setDefaultStyleSheet("""
            p { margin-top: 0; margin-bottom: 14px; line-height: 145%; }
            h1,h2,h3 { color: #cadbd4; margin-top: 22px; margin-bottom: 12px; }
            li { margin-bottom: 8px; }
            code,pre { font-family: 'Roboto Mono'; color: #c5d9d9; }
            pre { background-color: #1c2428; padding: 12px; white-space: pre-wrap; }
            blockquote { color: #a9b7bc; margin-left: 14px; }
        """)

    def setPlainText(self,value):
        self.document().setMarkdown(value,QTextDocument.MarkdownFeature.MarkdownDialectGitHub|QTextDocument.MarkdownFeature.MarkdownNoHTML)

    def loadResource(self,resource_type,url):
        return None
