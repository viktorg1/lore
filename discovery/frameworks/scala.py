from ..markers import ChoiceMarker, FileMarker, Option
from .base import Framework

PLAY = Framework(
    name="Play", languages=("scala",), deps=("org.playframework", "com.typesafe.play", "sbt-plugin"),
    markers=(
        FileMarker(id="play-constructor-injection", glob="app/controllers/**/*.scala", has=r"@Inject\(\)", min_applicable=3,
                   rule="Inject dependencies into controllers through the constructor with @Inject()."),
        ChoiceMarker(id="play-actions", glob="app/controllers/**/*.scala", min_applicable=5, options=(
            Option("Action.async", r"\bAction\.async\b", "Write actions as Action.async returning Future[Result]."),
            Option("sync Action", r"\bAction\s*\{", "Write actions as synchronous Action { ... } blocks."))),
    ),
)
FRAMEWORKS = [PLAY]
