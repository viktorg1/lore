from ..markers import AbsentMarker, ChoiceMarker, Option
from .base import Language

G = "**/*.dart"
LANGUAGE = Language(
    name="dart", extensions=("dart",), formatter_enforced=True, check_quotes=True,
    markers=(
        AbsentMarker(id="dart-print", glob=G, bad=r"^\s*print\(", rule="Use a logger (or debugPrint), not print()."),
        AbsentMarker(id="dart-dynamic", glob=G, bad=r"\bdynamic\b", rule="Avoid `dynamic`; use precise types."),
        ChoiceMarker(id="dart-imports", glob=G, options=(
            Option("package: imports", r"^import\s+'package:", "Import project files with package: URIs."),
            Option("relative imports", r"^import\s+'\.{1,2}/", "Import project files with relative paths."))),
    ),
)
