from ..markers import ChoiceMarker, FileMarker, Option
from .base import Framework

ANGULAR = Framework(
    name="Angular", languages=("typescript",), deps=("@angular/core",),
    markers=(
        FileMarker(id="angular-standalone", glob="**/*.ts", when=r"@Component\(", has=r"standalone:\s*true",
                   rule="Declare components with `standalone: true`."),
        FileMarker(id="angular-onpush", glob="**/*.ts", when=r"@Component\(", has=r"ChangeDetectionStrategy\.OnPush",
                   rule="Use ChangeDetectionStrategy.OnPush on components."),
        FileMarker(id="angular-selector-prefix", glob="**/*.ts", when=r"@Component\(", has=r"selector:\s*['\"]app-",
                   rule="Prefix component selectors with `app-`."),
        ChoiceMarker(id="angular-injection", glob="**/*.ts", options=(
            Option("inject()", r"\binject\(\s*[A-Z]", "Inject dependencies with the inject() function."),
            Option("constructor injection", r"constructor\(\s*(?:private|public|protected|readonly)\s", "Inject dependencies through constructor parameters."))),
        ChoiceMarker(id="angular-reactivity", glob="**/*.ts", options=(
            Option("signals", r"\b(?:signal|computed)(?:<[^>]*>)?\(", "Hold component state in signals."),
            Option("RxJS subjects", r"new\s+(?:Behavior)?Subject\b", "Hold shared state in RxJS (Behavior)Subjects."))),
    ),
)
FRAMEWORKS = [ANGULAR]
