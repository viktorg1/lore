from ..markers import AbsentMarker, ChoiceMarker, Option
from .base import Language

G = "**/*.{kt,kts}"
LANGUAGE = Language(
    name="kotlin", extensions=("kt", "kts"),
    markers=(
        AbsentMarker(id="kt-bang-bang", glob=G, bad=r"\w!!", rule="Avoid the !! operator; handle null explicitly."),
        AbsentMarker(id="kt-println", glob=G, bad=r"\bprintln\(", rule="Use the logger, not println()."),
        AbsentMarker(id="kt-global-scope", glob=G, bad=r"\bGlobalScope\.", rule="Do not launch coroutines in GlobalScope; use a structured scope."),
        AbsentMarker(id="kt-wildcard-import", glob=G, bad=r"^import\s+[\w.]+\.\*$", rule="Do not use wildcard imports."),
        ChoiceMarker(id="kt-val-var", glob=G, options=(
            Option("val", r"\bval\s+\w", "Prefer val over var; mutate state only where necessary."),
            Option("var", r"\bvar\s+\w"))),
    ),
)
