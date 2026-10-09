from ..markers import AbsentMarker, ChoiceMarker, Option
from .base import Framework

LOVE = Framework(
    name="LOVE", languages=("lua",), signatures=(r"love\.(?:load|update|draw)\b",), signature_files=1,
    markers=(
        ChoiceMarker(id="love-callbacks", glob="**/*.lua", min_applicable=3, options=(
            Option("function love.x()", r"^function\s+love\.\w+\(", "Define LÖVE callbacks as `function love.update(dt)`."),
            Option("love.x = function", r"^love\.\w+\s*=\s*function", "Define LÖVE callbacks as `love.update = function(dt)`."))),
        AbsentMarker(id="love-os-exit", glob="**/*.lua", bad=r"\bos\.exit\(", min_applicable=3, rule="Quit with love.event.quit(), not os.exit()."),
    ),
)
FRAMEWORKS = [LOVE]
