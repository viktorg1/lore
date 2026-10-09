from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Framework

DJANGO = Framework(
    name="Django", languages=("python",), deps=("django",),
    markers=(
        ChoiceMarker(id="django-views", glob="**/{views.py,views/*.py}", options=(
            Option("class-based views", r"^class\s+\w+\((?:[\w.]+,\s*)*[\w.]*(?:View|ViewSet|APIView)\)", "Write class-based views."),
            Option("function-based views", r"^def\s+\w+\(\s*request\b", "Write function-based views."))),
        FileMarker(id="django-model-str", glob="**/models.py", when=r"\(models\.Model\)", has=r"def __str__",
                   rule="Define __str__ on every model.", min_applicable=3),
        AbsentMarker(id="django-raw-sql", glob="**/*.py", bad=r"\.raw\(|cursor\.execute\(|\.extra\(",
                     rule="Use the ORM, not raw SQL (.raw/.extra/cursor.execute)."),
        AbsentMarker(id="django-null-strings", glob="**/models.py", bad=r"(?:Char|Text|Email|URL|Slug)Field\([^)\n]*null=True",
                     rule="Do not set null=True on string fields; use blank=True and an empty string."),
        ChoiceMarker(id="django-not-found", glob="**/*.py", options=(
            Option("get_object_or_404", r"\bget_object_or_404\(", "Use get_object_or_404() for lookups that should 404."),
            Option("try/except DoesNotExist", r"except\s+[\w.]*DoesNotExist", "Handle missing objects with try/except DoesNotExist."))),
    ),
)
FRAMEWORKS = [DJANGO]
