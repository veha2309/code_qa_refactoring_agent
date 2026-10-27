// Only bundled parsers are loaded. No target modules, config or plugins are imported.
import * as prettier from './prettier/standalone.mjs';
import * as babel from './prettier/plugins/babel.mjs';
import * as estree from './prettier/plugins/estree.mjs';
import * as typescript from './prettier/plugins/typescript.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
try {
  const {source, parser} = JSON.parse(input);
  if (!['babel', 'typescript', 'json', 'jsonc'].includes(parser)) throw new Error('Unsupported formatter parser');
  const formatted = await prettier.format(source, {
    parser, plugins: [babel, estree, typescript], printWidth: 88,
    tabWidth: 2, useTabs: false, endOfLine: 'lf', embeddedLanguageFormatting: 'off',
  });
  process.stdout.write(JSON.stringify({formatted}));
} catch (error) {
  process.stderr.write(String(error.message)); process.exitCode = 1;
}
