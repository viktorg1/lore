from ..markers import AbsentMarker, OccurrenceMarker
from .base import Framework

PHOENIX = Framework(
    name="Phoenix", languages=("elixir",), deps=("phoenix",),
    markers=(
        AbsentMarker(id="phoenix-repo-in-web", glob="lib/*_web/**/*.ex", bad=r"\bRepo\.", min_applicable=5,
                     rule="Do not call Repo from the web layer; go through a context module."),
        OccurrenceMarker(id="phoenix-impl", glob="lib/**/*.ex",
                         total=r"^\s*def\s+(?:mount|handle_event|handle_info|handle_params|handle_call|handle_cast|init)\(",
                         has=r"@impl\s+true\s*\n\s*def\s+(?:mount|handle_event|handle_info|handle_params|handle_call|handle_cast|init)\(",
                         rule="Mark callback implementations with @impl true."),
    ),
)
FRAMEWORKS = [PHOENIX]
