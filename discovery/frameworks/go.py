from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Framework

GIN = Framework(
    name="Gin", languages=("go",), deps=("gin-gonic/gin",),
    markers=(
        ChoiceMarker(id="gin-binding", glob="**/*.go", options=(
            Option("ShouldBind*", r"\.ShouldBind\w*\(", "Bind requests with ShouldBind*() and handle the error yourself."),
            Option("Bind*", r"\.Bind(?:JSON|Query|URI|Header|XML|YAML)?\(", "Bind requests with Bind*() (auto-400 on failure)."))),
        ChoiceMarker(id="gin-engine", glob="**/*.go", min_applicable=1, options=(
            Option("gin.New()", r"\bgin\.New\(\)", "Create the engine with gin.New() and add middleware explicitly."),
            Option("gin.Default()", r"\bgin\.Default\(\)", "Create the engine with gin.Default()."))),
        FileMarker(id="gin-route-groups", glob="**/*.go", when=r"\bgin\.(?:Default|New)\(\)", min_applicable=1, has=r"\.Group\(",
                   rule="Organise routes into router groups (r.Group(\"/api\"))."),
        AbsentMarker(id="gin-h-maps", glob="**/*.go", bad=r"\bgin\.H\{", rule="Respond with typed structs, not gin.H maps."),
    ),
)
FRAMEWORKS = [GIN]
