"""Rebase diagram-only annotations without overwriting newly extracted facts."""
from copy import deepcopy
import json
import sqlite3
import time
from .core import app_dir


def draft_store(project,scope,base=None,draft=None):
    """Small per-user annotation store; JSON only, never deserialize executable data."""
    with sqlite3.connect(app_dir()/'feature-drafts.sqlite3',timeout=.05) as db:
        db.execute('CREATE TABLE IF NOT EXISTS drafts(project TEXT, scope TEXT, modified REAL, payload TEXT, PRIMARY KEY(project,scope))')
        if draft is None:
            row=db.execute('SELECT payload FROM drafts WHERE project=? AND scope=?',(project,scope)).fetchone()
            if not row or len(row[0])>5_000_000:return None
            value=json.loads(row[0])
            from .design_canvas import validate_model
            validate_model(value['base']);validate_model(value['draft'])
            return value
        if draft==base:
            db.execute('DELETE FROM drafts WHERE project=? AND scope=?',(project,scope));return
        value=json.dumps({'base':base,'draft':draft},ensure_ascii=False)
        if len(value)>5_000_000:return
        db.execute('INSERT OR REPLACE INTO drafts VALUES(?,?,?,?)',(project,scope,time.time(),value))
        db.execute('DELETE FROM drafts WHERE rowid NOT IN (SELECT rowid FROM drafts ORDER BY modified DESC LIMIT 100)')


def rebase_draft(base,draft,fresh):
    result=deepcopy(fresh);overlays=[]
    for collection,keys in [('nodes',('title','fields','operations','x','y')),('edges',('label','classification'))]:
        original={r['id']:r for r in base.get(collection,[])}
        current={r['id']:r for r in result[collection]}
        edited={r['id']:r for r in draft.get(collection,[])}
        for key,row in edited.items():
            if key not in original:
                # User additions remain explicitly proposed.
                added=deepcopy(row);added['origin']='proposed';result[collection].append(added);continue
            changes={k:deepcopy(row[k]) for k in keys if row.get(k)!=original[key].get(k) and k in row}
            if changes:
                review=key not in current or any(current[key].get(k)!=original[key].get(k) for k in original[key] if k not in ('x','y','evidence'))
                overlays.append({'id':key,'collection':collection,'changes':changes,'needs_review':review})
                if key in current:current[key].update(changes);current[key]['annotation']=True
        for key in original.keys()-edited.keys():
            overlays.append({'id':key,'collection':collection,'hidden':True,'needs_review':key not in current or current[key]!=original[key]})
            result[collection]=[r for r in result[collection] if r['id']!=key]
    ids={r['id'] for r in result['nodes']}
    result['edges']=[r for r in result['edges'] if r['from'] in ids and r['to'] in ids]
    existing={(r['collection'],r['id']) for r in overlays}
    overlays.extend(deepcopy(r) for r in draft.get('draft_overlays',[]) if r.get('needs_review') and (r['collection'],r['id']) not in existing)
    result['draft_overlays']=overlays
    if any(r['needs_review'] for r in overlays):result['notice']+=' · Source changed: annotations need review.'
    return result
