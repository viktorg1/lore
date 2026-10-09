from ..markers import AbsentMarker, ChoiceMarker, FileMarker, OccurrenceMarker, Option
from .base import Language

G = "**/*.py"
LANGUAGE = Language(
    name="python", extensions=("py",), check_quotes=True,
    markers=(
        FileMarker(id="py-future-annotations", glob=G, has=r"from __future__ import annotations",
                   rule="Start Python modules with `from __future__ import annotations`."),
        OccurrenceMarker(id="py-return-annotations", glob=G, total=r"def\s+\w+\s*\(", has=r"def\s+\w+\s*\([^)]*\)\s*->",
                         rule="Annotate return types on every Python function."),
        FileMarker(id="py-module-docstring", glob=G, when=r"^(?:def|class)\s", exclude_tests=True, min_applicable=8,
                   has=r"\A\s*(?:#[^\n]*\n\s*)*[rR]?(?:\"\"\"|''')", rule="Give every module a docstring."),
        OccurrenceMarker(id="py-function-docstrings", glob=G, exclude_tests=True,
                         total=r"^\s*def\s+[a-z]\w*\([^)]*\)(?:\s*->\s*[^:]+)?:[ \t]*\n",
                         has=r"^\s*def\s+[a-z]\w*\([^)]*\)(?:\s*->\s*[^:]+)?:[ \t]*\n\s*[rR]?(?:\"\"\"|''')",
                         rule="Write a docstring on every function."),
        AbsentMarker(id="py-print", glob=G, bad=r"^\s*print\(", rule="Use the logging module, not print(), in application code."),
        AbsentMarker(id="py-bare-except", glob=G, bad=r"^\s*except\s*:", rule="Never use a bare `except:`; catch specific exceptions."),
        AbsentMarker(id="py-mutable-default", glob=G, bad=r"def\s+\w+\([^)]*=\s*(?:\[\]|\{\}|set\(\))",
                     rule="Do not use mutable default arguments; default to None and create inside."),
        AbsentMarker(id="py-wildcard-import", glob=G, bad=r"^from\s+\S+\s+import\s+\*", rule="Do not use wildcard imports."),
        AbsentMarker(id="py-shell", glob=G, bad=r"shell\s*=\s*True|\bos\.system\(",
                     rule="Do not use shell=True or os.system(); pass an argument list to subprocess."),
        ChoiceMarker(id="py-string-format", glob=G, options=(
            Option("f-strings", r"(?<![\w\"'])[fF][\"']", "Format strings with f-strings."),
            Option(".format()", r"[\"']\.format\(", "Format strings with str.format()."),
            Option("% formatting", r"[\"']\s*%\s*[\(\w]", "Format strings with % formatting."))),
        ChoiceMarker(id="py-paths", glob=G, options=(
            Option("pathlib", r"\bfrom pathlib import\b|\bPath\(", "Handle paths with pathlib.Path, not os.path."),
            Option("os.path", r"\bos\.path\.", "Handle paths with os.path."))),
        ChoiceMarker(id="py-optional-style", glob=G, options=(
            Option("X | None", r"\w\]?\s*\|\s*None\b", "Write optional types as `X | None`."),
            Option("typing.Optional", r"\bOptional\[|\bUnion\[", "Write optional types with typing.Optional/Union."))),
        ChoiceMarker(id="py-generics", glob=G, options=(
            Option("builtin generics", r"(?<![\w.])(?:list|dict|tuple|set)\[", "Use builtin generics (list[int], dict[str, int])."),
            Option("typing generics", r"\b(?:List|Dict|Tuple|Set)\[", "Use typing.List/Dict/Tuple/Set for generics."))),
    ),
)
