"""Small bundled vector glyphs, drawn locally without icon fonts or downloads."""
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


STYLES = {
    '.py': ('Py', '#80b9da'), '.js': ('JS', '#d9c578'),
    '.jsx': ('Js', '#80c6d0'), '.ts': ('TS', '#82afe0'),
    '.tsx': ('Ts', '#89c7d5'), '.dart': ('D', '#78c8d5'),
    '.java': ('J', '#d6a186'), '.cs': ('C#', '#b4a0d7'),
    '.go': ('Go', '#82c5cf'), '.rs': ('R', '#ceaa8f'),
    '.json': ('{}', '#d3bd83'), '.toml': ('=', '#b6a5d1'),
    '.yaml': ('Y', '#c5a2bd'), '.yml': ('Y', '#c5a2bd'),
    '.md': ('M', '#9ebacf'), '.txt': ('≡', '#9eacba'),
    '.html': ('<>', '#d5a087'), '.css': ('#', '#a7a3d4'),
    '.scss': ('#', '#c79db7'), '.svg': ('◇', '#cfbd88'),
}


@lru_cache(maxsize=96)
def _document(mark, color):
    pixmap = QPixmap(40, 40); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    outline = QPainterPath(); outline.moveTo(10, 5); outline.lineTo(25, 5)
    outline.lineTo(31, 11); outline.lineTo(31, 34); outline.lineTo(10, 34); outline.closeSubpath()
    painter.drawPath(outline); painter.drawLine(25, 5, 25, 11); painter.drawLine(25, 11, 31, 11)
    painter.fillRect(QRectF(6, 16, 29, 14), QColor('#1b2129'))
    font = QFont('Noto Sans'); font.setPixelSize(14 if len(mark) < 3 else 12); font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font); painter.drawText(QRectF(3, 13, 34, 19), Qt.AlignmentFlag.AlignCenter, mark)
    painter.end(); return QIcon(pixmap)


def file_icon(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if path.name.lower() in {'dockerfile', '.dockerignore'}: return _document('Dk', '#88b8d7')
    if path.name.lower() in {'.gitignore', '.gitattributes'}: return _document('git', '#d5a38d')
    return _document(*STYLES.get(suffix, ('≡', '#9eacba')))


@lru_cache(maxsize=64)
def folder_icon(name='', expanded=False):
    name = Path(name).name.lower()
    color = '#9eafc4'
    if name in {'src', 'lib', 'app', 'changelens'}: color = '#87b8b0'
    elif name in {'test', 'tests', '__tests__'}: color = '#b1c394'
    elif name in {'components', 'widgets', 'ui'}: color = '#b4a5cd'
    elif name in {'assets', 'resources', 'images', 'public'}: color = '#ceba8f'
    pixmap = QPixmap(40, 40); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    fill = QColor(color); fill.setAlpha(25); painter.setBrush(fill)
    back = QPainterPath(); back.moveTo(5, 12); back.lineTo(5, 31); back.lineTo(34, 31)
    back.lineTo(34, 12); back.lineTo(19, 12); back.lineTo(15, 8); back.lineTo(5, 8); back.closeSubpath(); painter.drawPath(back)
    front = QPainterPath(); front.moveTo(5, 31); front.lineTo(9 if expanded else 5, 17)
    front.lineTo(37 if expanded else 34, 17); front.lineTo(34, 31); front.closeSubpath(); painter.drawPath(front)
    painter.end(); return QIcon(pixmap)
