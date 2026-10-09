from ..markers import AbsentMarker
from .base import Language

G = "**/*.scala"
LANGUAGE = Language(
    name="scala", extensions=("scala",),
    markers=(
        AbsentMarker(id="scala-null", glob=G, bad=r"\bnull\b", rule="Do not use null; use Option."),
        AbsentMarker(id="scala-var", glob=G, bad=r"^\s*var\s+\w", rule="Prefer val over var; avoid mutable state."),
        AbsentMarker(id="scala-return", glob=G, bad=r"\breturn\b", rule="Do not use the return keyword; use expression results."),
        AbsentMarker(id="scala-println", glob=G, bad=r"\bprintln\(", rule="Use a logger, not println()."),
        AbsentMarker(id="scala-await", glob=G, bad=r"Await\.result", rule="Do not block on Futures with Await.result."),
    ),
)
