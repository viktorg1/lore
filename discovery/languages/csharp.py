from ..markers import AbsentMarker, ChoiceMarker, FileMarker, OccurrenceMarker, Option
from .base import Language

G = "**/*.cs"
LANGUAGE = Language(
    name="csharp", extensions=("cs",),
    markers=(
        OccurrenceMarker(id="cs-async-suffix", glob=G, total=r"\bTask(?:<[^>]+>)?\s+\w+\(", has=r"\bTask(?:<[^>]+>)?\s+\w+Async\(",
                         rule="Suffix async methods that return Task with `Async`."),
        OccurrenceMarker(id="cs-interface-prefix", glob=G, total=r"\binterface\s+\w+", has=r"\binterface\s+I[A-Z]\w*",
                         rule="Prefix interface names with `I`."),
        FileMarker(id="cs-file-scoped-namespace", glob=G, when=r"^namespace\s", has=r"^namespace\s+[\w.]+;",
                   rule="Use file-scoped namespaces (`namespace X;`)."),
        OccurrenceMarker(id="cs-xml-docs", glob=G, exclude_tests=True,
                         total=r"^\s*public\s+(?:sealed\s+|static\s+|abstract\s+|partial\s+)*(?:class|interface|record|struct|enum)\s+\w+",
                         has=r"///[^\n]*\n(?:\s*///[^\n]*\n)*\s*(?:\[[^\]\n]+\]\s*\n\s*)*public\s+(?:sealed\s+|static\s+|abstract\s+|partial\s+)*(?:class|interface|record|struct|enum)\s+\w+",
                         min_applicable=8, rule="Document public types with XML doc comments (/// <summary>)."),
        AbsentMarker(id="cs-console", glob=G, bad=r"Console\.Write", rule="Use the logging abstraction, not Console.Write*."),
        AbsentMarker(id="cs-block-on-task", glob=G, bad=r"\.Result\b|\.Wait\(\)|GetAwaiter\(\)\.GetResult",
                     rule="Do not block on tasks (.Result/.Wait()); await them."),
        AbsentMarker(id="cs-catch-generic", glob=G, bad=r"catch\s*\(\s*Exception\b", rule="Catch specific exceptions, not Exception."),
        AbsentMarker(id="cs-thread-sleep", glob=G, bad=r"Thread\.Sleep\(", rule="Use `await Task.Delay`, not Thread.Sleep."),
        ChoiceMarker(id="cs-var", glob=G, options=(
            Option("var", r"^\s*var\s+\w+\s*=", "Use `var` for local variables."),
            Option("explicit types", r"^\s*(?:string|int|long|bool|double|decimal|[A-Z]\w*(?:<[^>\n]+>)?)\s+\w+\s*=\s*(?:new\b|await\b|\w)",
                   "Declare local variables with explicit types, not `var`."))),
    ),
)
