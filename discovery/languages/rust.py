from ..markers import AbsentMarker, FileMarker, OccurrenceMarker
from .base import Language

G = "**/*.rs"
LANGUAGE = Language(
    name="rust", extensions=("rs",), formatter_enforced=True,
    markers=(
        AbsentMarker(id="rs-unwrap", glob=G, bad=r"\.unwrap\(\)", rule="Avoid .unwrap() in non-test code; propagate errors with `?`."),
        AbsentMarker(id="rs-println", glob=G, bad=r"\b(?:println|eprintln|dbg)!\(", rule="Use the logging/tracing macros, not println!/dbg!."),
        AbsentMarker(id="rs-unsafe", glob=G, bad=r"\bunsafe\b", rule="Do not write `unsafe` code."),
        AbsentMarker(id="rs-panic-macros", glob=G, bad=r"\b(?:panic|todo|unimplemented)!\(", rule="No panic!/todo!/unimplemented! in production code; return errors."),
        OccurrenceMarker(id="rs-doc-pub", glob=G, exclude_tests=True,
                         total=r"^\s*pub\s+(?:async\s+)?(?:fn|struct|enum|trait)\s+\w+",
                         has=r"///[^\n]*\n(?:\s*(?:///|#\[)[^\n]*\n)*\s*pub\s+(?:async\s+)?(?:fn|struct|enum|trait)\s+\w+",
                         rule="Document public items with /// doc comments."),
        FileMarker(id="rs-crate-lints", glob="**/{lib,main}.rs", min_applicable=1, has=r"^#!\[(?:deny|forbid|warn)\(",
                   rule="Keep crate-level #![deny(...)]/#![warn(...)] lint attributes in lib.rs/main.rs."),
    ),
)
