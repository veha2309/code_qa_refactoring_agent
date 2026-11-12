"""Prepare the pinned TypeScript language service for offline refactoring."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request


VERSION = "5.9.3"
INTEGRITY = "jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw=="


def main():
    url = f"https://registry.npmjs.org/typescript/-/typescript-{VERSION}.tgz"
    with urllib.request.urlopen(url, timeout=90) as response:
        archive = response.read()
    if base64.b64encode(hashlib.sha512(archive).digest()).decode() != INTEGRITY:
        raise ValueError("TypeScript package integrity mismatch")
    root = Path(__file__).resolve().parents[1] / "resources" / "refactoring" / "node_modules" / "typescript"
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        names = ["LICENSE.txt", "ThirdPartyNoticeText.txt"]
        names.extend(name.removeprefix("package/") for name in tar.getnames()
                     if name.startswith("package/lib/lib.") and name.endswith(".d.ts"))
        names.append("lib/typescript.js")
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile("package/" + name).read())
    print(f"TypeScript {VERSION} refactoring assets ready.")


if __name__ == "__main__":
    main()
