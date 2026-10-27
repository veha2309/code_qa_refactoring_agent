"""Vendor pinned formatter assets once; application formatting is fully offline."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

VERSION='3.9.10'
INTEGRITY='skGHTH1Yb9QvaTC4hWnRTzEYtCpApF0UMBPz+t/0ZPzP8ihefo/btKd+QA7pUE0fEwA1SbS/NmhyEcstdXOIdA=='
NODE_VERSION='24.12.0'


def fetch(url):
    with urllib.request.urlopen(url,timeout=90) as response:return response.read()


def main():
    root=Path(__file__).resolve().parents[1]/'resources'/'formatting';root.mkdir(parents=True,exist_ok=True)
    archive=fetch(f'https://registry.npmjs.org/prettier/-/prettier-{VERSION}.tgz')
    if base64.b64encode(hashlib.sha512(archive).digest()).decode()!=INTEGRITY:raise ValueError('Prettier integrity mismatch')
    names=['standalone.mjs','plugins/babel.mjs','plugins/estree.mjs','plugins/typescript.mjs','LICENSE']
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        for name in names:
            data=tar.extractfile('package/'+name).read();target=root/'prettier'/name
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    sums=fetch(f'https://nodejs.org/dist/v{NODE_VERSION}/SHASUMS256.txt').decode()
    expected=next(line.split()[0] for line in sums.splitlines() if line.split()[-1]=='win-x64/node.exe')
    node=shutil.which('node');raw=Path(node).read_bytes() if node else b''
    if hashlib.sha256(raw).hexdigest()!=expected:raw=fetch(f'https://nodejs.org/dist/v{NODE_VERSION}/win-x64/node.exe')
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Node integrity mismatch')
    (root/'node.exe').write_bytes(raw)
    (root/'NODE_LICENSE').write_bytes(fetch(f'https://raw.githubusercontent.com/nodejs/node/v{NODE_VERSION}/LICENSE'))
    manifest={'prettier':VERSION,'node':NODE_VERSION,'prettier_integrity':'sha512-'+INTEGRITY,
        'files':{path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in root.rglob('*') if path.is_file() and path.name not in {'manifest.json','worker.mjs'}}}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Offline formatter assets ready:',root)


if __name__=='__main__':main()
