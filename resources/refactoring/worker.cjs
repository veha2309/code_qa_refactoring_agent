"use strict";

const fs = require("node:fs");
const path = require("node:path");
const ts = require("./node_modules/typescript/lib/typescript.js");

function run(request) {
  const absolute = (name) => path.resolve(request.root, name);
  const key = (name) => {
    const resolved = absolute(name);
    return ts.sys.useCaseSensitiveFileNames ? resolved : resolved.toLowerCase();
  };
  const files = new Map(Object.entries(request.files).map(([name, text]) => [key(name), text]));
  const original = new Map(files);
  const sourceFile = key(request.path);
  const defaults = {
    allowJs: true, noEmit: true, target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, jsx: ts.JsxEmit.Preserve,
  };
  let options = defaults;
  for (let folder = path.dirname(sourceFile); ; folder = path.dirname(folder)) {
    const config = ["tsconfig.json", "jsconfig.json"].map((name) => path.join(folder, name)).find(ts.sys.fileExists);
    if (config) {
      const parsed = ts.getParsedCommandLineOfConfigFile(config, {}, {
        ...ts.sys,
        onUnRecoverableConfigFileDiagnostic(error) {
          throw new Error(ts.flattenDiagnosticMessageText(error.messageText, "\n"));
        },
      });
      if (parsed) options = { ...defaults, ...parsed.options, allowJs: true, noEmit: true };
      break;
    }
    if (key(folder) === key(request.root) || folder === path.dirname(folder)) break;
  }
  let version = 0;
  const readFile = (name) => files.get(key(name)) ?? ts.sys.readFile(name);
  const service = ts.createLanguageService({
    ...ts.sys,
    getCompilationSettings: () => options,
    getCurrentDirectory: () => request.root,
    getDefaultLibFileName: ts.getDefaultLibFilePath,
    getScriptFileNames: () => [...files.keys()],
    getScriptVersion: () => String(version),
    getProjectVersion: () => String(version),
    getScriptSnapshot(name) {
      const text = readFile(name);
      return text === undefined ? undefined : ts.ScriptSnapshot.fromString(text);
    },
    readFile,
    fileExists: (name) => files.has(key(name)) || ts.sys.fileExists(name),
  });
  const preferences = { providePrefixAndSuffixTextForRename: true };
  const { newName } = request;
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, false, ts.LanguageVariant.Standard, newName);
  const nameKind = scanner.scan();
  const contextual = nameKind >= ts.SyntaxKind.FirstContextualKeyword && nameKind <= ts.SyntaxKind.LastContextualKeyword;
  if ((nameKind !== ts.SyntaxKind.Identifier && !contextual) || scanner.getTokenText() !== newName) {
    throw new Error("Enter a valid JavaScript or TypeScript name.");
  }

  function applyChanges(edits) {
    for (const { fileName, textChanges, isNewFile } of edits) {
      const file = key(fileName);
      let text = files.get(file);
      if (text === undefined || isNewFile) {
        throw new Error("This refactor would change a file outside the indexed workspace.");
      }
      let boundary = text.length;
      for (const { span, newText } of [...textChanges].sort((a, b) => b.span.start - a.span.start)) {
        const end = span.start + span.length;
        if (span.start < 0 || end > boundary) throw new Error("The language service returned overlapping edits.");
        text = text.slice(0, span.start) + newText + text.slice(end);
        boundary = span.start;
      }
      files.set(file, text);
    }
    version++;
  }

  function rename(fileName, position) {
    const info = service.getRenameInfo(fileName, position, preferences);
    if (!info.canRename) throw new Error(info.localizedErrorMessage);
    if (info.fileToRename) throw new Error("Choose a code name. Renaming files is a separate action.");
    if (info.displayName === newName) throw new Error("Choose a different name.");
    const references = service.findRenameLocations(fileName, position, false, false, preferences);
    if (!references?.length) throw new Error("No references could be resolved for this name.");
    const program = service.getProgram();
    const checker = program.getTypeChecker();
    const edits = new Map();
    for (const reference of references) {
      const target = key(reference.fileName);
      if (!files.has(target)) throw new Error("This name has references outside the indexed workspace.");
      const source = program.getSourceFile(target);
      const token = ts.getTokenAtPosition(source, reference.textSpan.start);
      const scope = ts.SymbolFlags.Value | ts.SymbolFlags.Type | ts.SymbolFlags.Namespace | ts.SymbolFlags.Alias;
      const owner = checker.getSymbolAtLocation(token)?.parent;
      const escaped = ts.escapeLeadingUnderscores(newName);
      const receiver = ts.isPropertyAccessExpression(token.parent)
        ? checker.getTypeAtLocation(token.parent.expression) : undefined;
      if (owner?.members?.has(escaped) || owner?.exports?.has(escaped) || receiver?.getProperty(newName)
          || checker.getSymbolsInScope(token, scope).some((symbol) => symbol.getName() === newName)) {
        throw new Error(`“${newName}” is already defined in a scope affected by this rename.`);
      }
      if (!edits.has(target)) edits.set(target, { fileName: target, textChanges: [] });
      edits.get(target).textChanges.push({
        span: reference.textSpan,
        newText: (reference.prefixText || "") + newName + (reference.suffixText || ""),
      });
    }
    applyChanges(edits.values());
    return info.displayName;
  }

  let oldName;
  if (request.operation === "rename") {
    oldName = rename(sourceFile, request.start);
  } else {
    const range = { pos: request.start, end: request.end };
    const prefix = request.operation === "extract_method" ? "function_scope_" : "constant_scope_";
    const candidates = service.getApplicableRefactors(sourceFile, range, preferences, "invoked");
    const refactor = candidates.find(({ actions }) => actions.some((action) =>
      action.name.startsWith(prefix) && !action.notApplicableReason));
    if (!refactor) throw new Error(request.operation === "extract_method"
      ? "Select a complete expression or a block of statements to extract into a function."
      : "Select a complete expression to extract into a constant.");
    const action = refactor.actions.find((item) => item.name.startsWith(prefix) && !item.notApplicableReason);
    const result = service.getEditsForRefactor(sourceFile, {
      indentSize: 2, tabSize: 2, convertTabsToSpaces: true, newLineCharacter: "\n",
      insertSpaceBeforeAndAfterBinaryOperators: true, insertSpaceAfterCommaDelimiter: true,
    }, range, refactor.name, action.name, preferences);
    if (!result?.edits?.length) throw new Error("The language service could not extract that selection.");
    applyChanges(result.edits);
    if (result.renameLocation === undefined) throw new Error("The new declaration could not be located.");
    const renameFile = key(result.renameFilename || sourceFile);
    const generated = service.getRenameInfo(renameFile, result.renameLocation, preferences);
    if (!generated.canRename) throw new Error(generated.localizedErrorMessage);
    if (generated.displayName !== newName) rename(renameFile, result.renameLocation);
    oldName = "selection";
  }

  const changed = [...files].filter(([name, text]) => original.get(name) !== text);
  for (const [name] of changed) {
    const diagnostics = service.getSyntacticDiagnostics(name);
    if (diagnostics.length) throw new Error(ts.flattenDiagnosticMessageText(diagnostics[0].messageText, "\n"));
  }
  return { oldName, files: changed.map(([name, after]) => ({
    path: path.relative(request.root, name).split(path.sep).join("/"), after,
  })) };
}

try {
  const request = JSON.parse(fs.readFileSync(0, "utf8"));
  process.stdout.write(JSON.stringify(run(request)));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.message }));
  process.exitCode = 1;
}
