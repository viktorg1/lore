from ..markers import AbsentMarker, OccurrenceMarker
from .base import Language

G = "**/*.java"
LANGUAGE = Language(
    name="java", extensions=("java",),
    markers=(
        AbsentMarker(id="java-sysout", glob=G, bad=r"System\.(out|err)\.print", rule="Use the logger, not System.out/System.err."),
        AbsentMarker(id="java-print-stack-trace", glob=G, bad=r"\.printStackTrace\(", rule="Log exceptions with the logger, not printStackTrace()."),
        AbsentMarker(id="java-catch-generic", glob=G, bad=r"catch\s*\(\s*(?:Exception|Throwable)\s+\w+\s*\)", rule="Catch specific exceptions, not Exception/Throwable."),
        AbsentMarker(id="java-legacy-time", glob=G, bad=r"\bnew\s+Date\(|SimpleDateFormat|Calendar\.getInstance",
                     rule="Use java.time (Instant, LocalDate, ...), not Date/Calendar/SimpleDateFormat."),
        AbsentMarker(id="java-wildcard-import", glob=G, bad=r"^import\s+[\w.]+\.\*;", rule="Do not use wildcard imports."),
        OccurrenceMarker(id="java-javadoc-types", glob=G, exclude_tests=True,
                         total=r"^public\s+(?:final\s+|abstract\s+)*(?:class|interface|enum|record)\s+\w+",
                         has=r"\*/\s*\n(?:@\w+(?:\([^)]*\))?\s*\n)*public\s+(?:final\s+|abstract\s+)*(?:class|interface|enum|record)\s+\w+",
                         min_applicable=8, rule="Document public types with a Javadoc block."),
    ),
)
