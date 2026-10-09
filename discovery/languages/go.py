from ..markers import AbsentMarker, FileMarker, OccurrenceMarker
from .base import Language

G = "**/*.go"
LANGUAGE = Language(
    name="go", extensions=("go",), formatter_enforced=True,
    markers=(
        AbsentMarker(id="go-panic", glob=G, bad=r"\bpanic\(", rule="Return errors instead of calling panic() outside startup code."),
        AbsentMarker(id="go-fmt-print", glob=G, bad=r"\bfmt\.Print", rule="Use the project's logger, not fmt.Print*."),
        AbsentMarker(id="go-empty-interface", glob=G, bad=r"\binterface\{\}", rule="Use `any` instead of interface{}."),
        AbsentMarker(id="go-init", glob=G, bad=r"^func init\(\)", rule="Avoid init() functions; wire dependencies explicitly."),
        AbsentMarker(id="go-ioutil", glob=G, bad=r"\bioutil\.", rule="Do not use the deprecated io/ioutil package."),
        OccurrenceMarker(id="go-wrap-errors", glob=G, total=r"fmt\.Errorf\(", has=r"fmt\.Errorf\([^)]*%w",
                         rule="Wrap errors with fmt.Errorf(\"...: %w\", err) to keep the chain."),
        FileMarker(id="go-table-tests", glob="**/*_test.go", when=r"^func Test", has=r"(?:tests|cases|tt)\s*:?=\s*\[\]struct",
                   rule="Write table-driven tests ([]struct cases looped with t.Run)."),
    ),
)
