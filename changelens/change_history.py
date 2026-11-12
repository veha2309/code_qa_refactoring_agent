"""Local saved-file history and conflict-checked restoration. No Git reset."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .core import app_dir


@contextmanager
def db():
    conn=sqlite3.connect(app_dir()/'file-history.sqlite3',timeout=10)
    conn.execute('CREATE TABLE IF NOT EXISTS changes (id INTEGER PRIMARY KEY, path TEXT NOT NULL, created REAL, before BLOB, after BLOB, origin TEXT)')
    try:
        yield conn;conn.commit()
    except Exception:
        conn.rollback();raise
    finally:conn.close()


def record(path,before,after,origin='save'):
    if before==after:return
    with db() as conn:
        conn.execute('INSERT INTO changes(path,created,before,after,origin) VALUES(?,?,?,?,?)',(str(Path(path).resolve()),time.time(),before,after,origin))
        conn.execute('DELETE FROM changes WHERE path=? AND id NOT IN (SELECT id FROM changes WHERE path=? ORDER BY id DESC LIMIT 30)',(str(Path(path).resolve()),str(Path(path).resolve())))


def versions(path):
    path=Path(path).resolve()
    with db() as conn:
        rows=[{'id':r[0],'created':r[1],'before':bytes(r[2]),'after':bytes(r[3]),'origin':r[4]} for r in conn.execute('SELECT id,created,before,after,origin FROM changes WHERE path=? ORDER BY id DESC LIMIT 30',(str(path),))]
    backups=app_dir()/'backups'
    if backups.exists():
        folders=sorted((p for p in backups.iterdir() if p.is_dir() and not p.is_symlink()),key=lambda p:p.stat().st_mtime,reverse=True)[:200]
        for folder in folders:
            try:
                manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                for index,item in enumerate(manifest['files']):
                    if (Path(manifest['root'])/item['path']).resolve()!=path:continue
                    original=folder/(str(index)+'.original')
                    if original.is_symlink() or original.stat().st_size>2_000_000:continue
                    raw=original.read_bytes()
                    if any(r['before']==raw for r in rows):continue
                    rows.append({'id':'backup:'+folder.name+':'+str(index),'created':folder.stat().st_mtime,'before':raw,'after':b'','origin':'refactoring backup'})
            except (OSError,ValueError,KeyError,TypeError):continue
    return sorted(rows,key=lambda r:r['created'],reverse=True)[:30]


def restore(path,version_id,expected_digest):
    from .workspace import Document
    doc=Document(Path(path))
    if doc.digest!=expected_digest:raise ValueError('File changed after the preview. Reopen history before restoring.')
    row=next((r for r in versions(doc.path) if str(r['id'])==str(version_id)),None)
    if row is None:raise ValueError('Saved version is no longer available.')
    doc.save_raw(row['before'],origin='restore')
    return doc
