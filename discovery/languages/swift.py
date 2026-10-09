from ..markers import AbsentMarker
from .base import Language

G = "**/*.swift"
LANGUAGE = Language(
    name="swift", extensions=("swift",),
    markers=(
        AbsentMarker(id="swift-force-unwrap", glob=G, bad=r"[\w\)\]]!(?=[.\s),\]])", rule="Avoid force unwrapping (!); use guard/if let."),
        AbsentMarker(id="swift-try-bang", glob=G, bad=r"\btry!", rule="Do not use try!; handle or propagate the error."),
        AbsentMarker(id="swift-force-cast", glob=G, bad=r"\bas!\s", rule="Do not use as!; use as? and handle failure."),
        AbsentMarker(id="swift-print", glob=G, bad=r"^\s*print\(", rule="Use os.Logger, not print()."),
    ),
)
