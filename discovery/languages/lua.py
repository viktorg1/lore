from ..markers import AbsentMarker
from .base import Language

G = "**/*.lua"
LANGUAGE = Language(
    name="lua", extensions=("lua",), check_quotes=True,
    markers=(
        AbsentMarker(id="lua-global-function", glob=G, bad=r"^function\s+\w+\s*\(", rule="Declare functions `local` (or attach them to a module table)."),
        AbsentMarker(id="lua-print", glob=G, bad=r"^\s*print\(", rule="Use a logger, not print()."),
    ),
)
