from ..markers import AbsentMarker, ChoiceMarker, OccurrenceMarker, Option
from .base import Language

G = "**/*.{ts,tsx,mts}"
LANGUAGE = Language(
    name="typescript", extensions=("ts", "tsx", "mts"), check_quotes=True, check_semicolons=True,
    markers=(
        AbsentMarker(id="ts-any", glob=G, bad=r":\s*any\b|\bas any\b|<any>",
                     rule="Avoid the `any` type; use a precise type or `unknown`."),
        AbsentMarker(id="ts-ignore", glob=G, bad=r"@ts-ignore|@ts-nocheck",
                     rule="Do not use @ts-ignore/@ts-nocheck; fix the type (or use @ts-expect-error with a reason)."),
        AbsentMarker(id="ts-non-null", glob=G, bad=r"[\w\)\]]!(?:\.|\[|\))",
                     rule="Avoid non-null assertions (`!`); narrow the type instead."),
        AbsentMarker(id="ts-enum", glob=G, bad=r"^\s*(?:export\s+)?(?:declare\s+)?(?:const\s+)?enum\s",
                     rule="Avoid TypeScript enums; use union types or `as const` objects."),
        AbsentMarker(id="ts-double-cast", glob=G, bad=r"\bas unknown as\b",
                     rule="Do not double-cast through `unknown`; model the type correctly."),
        OccurrenceMarker(id="ts-import-type", glob=G, min_ratio=0.5,
                         total=r"^import\s+(?:type\s+)?\{[^}]*\}\s+from", has=r"^import\s+type\b",
                         rule="Use `import type` for type-only imports."),
        OccurrenceMarker(id="ts-export-return-types", glob=G, exclude_tests=True,
                         total=r"^export\s+(?:async\s+)?function\s+\w+\s*(?:<[^>]*>)?\([^)]*\)",
                         has=r"^export\s+(?:async\s+)?function\s+\w+\s*(?:<[^>]*>)?\([^)]*\)\s*:\s*\S",
                         rule="Annotate return types on exported functions."),
        ChoiceMarker(id="ts-object-shapes", glob=G, options=(
            Option("interface", r"^(?:export\s+)?interface\s+\w+", "Declare object shapes with `interface`."),
            Option("type alias", r"^(?:export\s+)?type\s+\w+(?:<[^>]*>)?\s*=\s*\{", "Declare object shapes with `type` aliases, not interface."))),
        ChoiceMarker(id="ts-array-types", glob=G, options=(
            Option("T[]", r"[\w>\]\)]\[\]", "Write array types as T[]."),
            Option("Array<T>", r"\bArray<", "Write array types as Array<T>."))),
    ),
)
