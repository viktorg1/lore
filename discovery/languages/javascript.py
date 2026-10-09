from ..markers import AbsentMarker, ChoiceMarker, FileMarker, OccurrenceMarker, Option
from .base import Language

G = "**/*.{js,jsx,mjs,cjs}"
LANGUAGE = Language(
    name="javascript", extensions=("js", "jsx", "mjs", "cjs"), check_quotes=True, check_semicolons=True,
    markers=(
        ChoiceMarker(id="js-modules", glob=G, options=(
            Option("ES modules", r"^(?:import\s[^;\n]*\sfrom\s|import\s+['\"]|export\s+(?:default|const|function|class|async|\{))",
                   "Use ES modules (import/export), not CommonJS require()."),
            Option("CommonJS", r"\brequire\(\s*['\"]|\bmodule\.exports\b",
                   "Use CommonJS (require/module.exports); do not mix in ES import/export."))),
        ChoiceMarker(id="js-async-style", glob=G, options=(
            Option("async/await", r"\bawait\s", "Use async/await instead of .then() chains."),
            Option(".then chains", r"\.then\(", "Use promise .then() chains; do not mix with async/await."))),
        ChoiceMarker(id="js-function-style", glob=G, options=(
            Option("arrow functions", r"^(?:export\s+)?const\s+\w+\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>",
                   "Define named functions as const arrow functions."),
            Option("function declarations", r"^(?:export\s+)?(?:async\s+)?function\s+\w+\s*\(",
                   "Define named functions with function declarations."))),
        ChoiceMarker(id="js-exports", glob=G, options=(
            Option("named exports", r"^export\s+(?:const|let|function|class|async\s+function)\s", "Use named exports; avoid default exports."),
            Option("default exports", r"^export\s+default\b", "Use default exports for a module's main value."))),
        ChoiceMarker(id="js-strings", glob=G, options=(
            Option("template literals", r"`[^`\n]*\$\{", "Build strings with template literals, not + concatenation."),
            Option("concatenation", r"['\"]\s*\+\s*[A-Za-z_]|[A-Za-z_\)]\s*\+\s*['\"]", "Concatenate strings with +; template literals are not used here."))),
        AbsentMarker(id="js-console", glob="**/*.{js,jsx,mjs,cjs,ts,tsx,vue,svelte}", bad=r"\bconsole\.(log|debug)\(",
                     rule="Do not leave console.log/debug calls in application code."),
        AbsentMarker(id="js-var", glob="**/*.{js,jsx,mjs,cjs,ts,tsx,vue}", bad=r"^\s*var\s+\w",
                     rule="Use const/let, not var."),
        AbsentMarker(id="js-loose-equality", glob=G, bad=r"[^=!<>]==[^=]|!=[^=]",
                     rule="Use strict equality (=== / !==), never == / !=."),
        AbsentMarker(id="js-eval", glob=G, bad=r"\beval\(|new Function\(", rule="Do not use eval() or new Function()."),
        FileMarker(id="js-use-strict", glob="**/*.{js,cjs}", when=r"\brequire\(|module\.exports", min_applicable=8,
                   has=r"^\s*['\"]use strict['\"]", rule="Start CommonJS scripts with 'use strict'."),
        OccurrenceMarker(id="js-jsdoc-exports", glob=G, exclude_tests=True,
                         total=r"^export\s+(?:default\s+)?(?:async\s+)?function\s+\w+",
                         has=r"\*/\s*\n\s*export\s+(?:default\s+)?(?:async\s+)?function\s+\w+",
                         rule="Document exported functions with a JSDoc block."),
    ),
)
