"""Language registry and manifest hints. Configuration is read, never executed."""
import json
from pathlib import Path

EXTENSIONS={".py":"python",".js":"javascript",".jsx":"javascript",".mjs":"javascript",".cjs":"javascript",
            ".ts":"typescript",".tsx":"tsx",".mts":"typescript",".cts":"typescript",
            ".java":"java",".cs":"csharp",".go":"go",".rs":"rust",".dart":"dart"}
NAMES={"python":"Python","javascript":"JavaScript / JSX","typescript":"TypeScript","tsx":"TypeScript / TSX",
       "java":"Java","csharp":"C#","go":"Go","rust":"Rust","dart":"Dart / Flutter"}
CONFIGS={"package.json","tsconfig.json","jsconfig.json","pyproject.toml","requirements.txt","go.mod","Cargo.toml","pom.xml","build.gradle","build.gradle.kts"}
CONFIGS.update({'pubspec.yaml','pubspec.yml','pubspec.lock','analysis_options.yaml'})


def language_for(path):return EXTENSIONS.get(Path(path).suffix.lower())
def is_source(path):return language_for(path) is not None
def is_config(path):return Path(path).name in CONFIGS or Path(path).suffix.lower()==".csproj"
def is_indexable(path):return is_source(path) or is_config(path)


def json_config(text):
    """JSONC comments/trailing commas, without altering quoted text or evaluating JS."""
    out=[]; index=0; quoted=False
    while index<len(text):
        char=text[index]
        if quoted:
            out.append(char)
            if char=="\\" and index+1<len(text):out.append(text[index+1]);index+=2;continue
            if char=='"':quoted=False
        elif char=='"':quoted=True;out.append(char)
        elif text[index:index+2]=="//":
            end=text.find("\n",index+2); index=len(text) if end<0 else end;continue
        elif text[index:index+2]=="/*":
            end=text.find("*/",index+2)
            if end<0:raise ValueError("Unclosed configuration comment")
            out.append(" "); index=end+2;continue
        else:out.append(char)
        index+=1
    # Remove trailing commas after comments have gone, keeping strings intact.
    clean="".join(out); out=[]; index=0; quoted=False
    while index<len(clean):
        char=clean[index]
        if quoted:
            out.append(char)
            if char=="\\" and index+1<len(clean):out.append(clean[index+1]);index+=2;continue
            if char=='"':quoted=False
        elif char=='"':quoted=True;out.append(char)
        elif char==",":
            after=index+1
            while after<len(clean) and clean[after].isspace():after+=1
            if after<len(clean) and clean[after] in "}]":index+=1;continue
            out.append(char)
        else:out.append(char)
        index+=1
    value=json.loads("".join(out))
    if not isinstance(value,dict):raise ValueError("Configuration must be an object")
    return value


def capabilities(language):
    semantic=language in {"python","javascript","typescript","tsx","dart"}
    return {"language":NAMES[language],"syntax":"AST","symbols":True,
            "impact":"resolved lexical references plus labeled inferences" if semantic else "structural file/module dependencies; symbol call resolution unavailable",
            "test_discovery":"pytest" if language=="python" else 'literal Dart test/testWidgets callbacks' if language=='dart' else "declared JS/TS test callbacks" if semantic else "named test declarations (structural)",
            "test_execution":"pytest" if language=="python" else 'prepared Flutter SDK and project dependencies; selected files after trust' if language=='dart' else "installed Jest/Vitest or Node test runner (selected files)" if semantic else "recommendations only",
            "static_completion":language=="python","local_ai":True,"ai_rewrite":True,"reviewed_refactoring":language=="python"}


def project_profile(root,hashes):
    counts={}; frameworks=[]; manifests={}; warnings=[]
    for path,digest in hashes.items():
        language=language_for(path)
        if language:counts[language]=counts.get(language,0)+1
        if not is_config(path) or digest in {"oversized","unreadable"}:continue
        try:text=(Path(root)/path).read_text(encoding="utf-8-sig")
        except (OSError,UnicodeError) as exc:warnings.append(f"Cannot read configuration {path}: {exc}");continue
        if Path(path).name in {"package.json","tsconfig.json","jsconfig.json"}:
            try:manifests[path]=json_config(text)
            except ValueError as exc:warnings.append(f"Cannot read configuration {path}: {exc}");continue
        hints=[]
        if Path(path).name=="package.json":
            data=manifests[path]; deps={**data.get("dependencies",{}),**data.get("devDependencies",{})} if isinstance(data.get("dependencies",{}),dict) and isinstance(data.get("devDependencies",{}),dict) else {}
            for package,label in {"react":"React","next":"Next.js","express":"Express","@nestjs/core":"NestJS","@angular/core":"Angular","vue":"Vue","svelte":"Svelte","vitest":"Vitest","jest":"Jest"}.items():
                if package in deps:hints.append((label,f"declared dependency {package}"))
            if isinstance(data.get("engines"),dict) and "node" in data["engines"]:hints.append(("Node.js","engines.node declaration"))
            for package,suffix in (("vue",".vue"),("svelte",".svelte")):
                if package in deps:warnings.append(f"{package} detected in {path}: {suffix} single-file components are not parsed; only supported script files are indexed.")
            if "@angular/core" in deps:warnings.append(f"Angular detected in {path}: template bindings and dependency-injection wiring are not resolved.")
        elif Path(path).name in {"requirements.txt","pyproject.toml"}:
            import re
            for package,label in {"django":"Django","flask":"Flask","fastapi":"FastAPI"}.items():
                if re.search(r"(?im)(?:^|[\s\"'])"+package+r"(?:\s|[\"'\[<=>!~])",text):hints.append((label,"dependency declaration hint"))
        elif Path(path).name=="pom.xml" and "spring-boot" in text:hints.append(("Spring Boot","Maven dependency hint"))
        elif path.endswith(".csproj") and "Microsoft.NET.Sdk.Web" in text:hints.append(("ASP.NET Core","Web SDK declaration"))
        elif Path(path).name=="go.mod":
            if "github.com/gin-gonic/gin" in text:hints.append(("Gin","Go module requirement"))
            if "github.com/labstack/echo" in text:hints.append(("Echo","Go module requirement"))
        elif Path(path).name=="Cargo.toml":
            if "actix-web" in text:hints.append(("Actix Web","Cargo dependency hint"))
            if "axum" in text:hints.append(("Axum","Cargo dependency hint"))
        elif Path(path).name in {'pubspec.yaml','pubspec.yml'}:
            import re
            name=re.search(r'(?m)^name:\s*([a-zA-Z_][\w]*)\s*$',text)
            flutter=bool(re.search(r'(?m)^\s+sdk:\s*flutter\s*(?:#.*)?$',text))
            manifests[path]={'package_name':name.group(1) if name else '', 'flutter':flutter}
            if flutter:hints.append(('Flutter','pubspec SDK dependency flutter'))
        for label,evidence in hints:frameworks.append({"name":label,"path":path,"evidence":evidence,"note":"Detected declaration, not proof of runtime architecture or complete framework support."})
    return {"languages":counts,"frameworks":frameworks,"capabilities":{key:capabilities(key) for key in counts},"manifests":manifests,"warnings":warnings}
