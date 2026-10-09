from ..markers import AbsentMarker, FileMarker, OccurrenceMarker
from .base import Language

G = "**/*.php"
LANGUAGE = Language(
    name="php", extensions=("php",), check_quotes=True,
    markers=(
        FileMarker(id="php-strict", glob=G, when=r"^<\?php", exclude_tests=True,
                   has=r"declare\(strict_types=1\)", rule="Declare strict_types=1 at the top of every PHP file."),
        OccurrenceMarker(id="php-return-types", glob=G,
                         total=r"function\s+\w+\s*\(", has=r"function\s+\w+\s*\([^)]*\)\s*:\s*[\w?\\|]",
                         rule="Give every PHP function and method an explicit return type."),
        OccurrenceMarker(id="php-property-types", glob=G,
                         total=r"^\s*(?:public|protected|private)\s+(?:static\s+)?(?:readonly\s+)?(?:\??[\w\\|]+\s+)?\$\w+",
                         has=r"^\s*(?:public|protected|private)\s+(?:static\s+)?(?:readonly\s+)?\??[\w\\|]+\s+\$\w+",
                         rule="Declare a type on every class property."),
        FileMarker(id="php-final-class", glob=G, when=r"^(?:abstract\s+)?(?:final\s+)?class\s", exclude_tests=True,
                   has=r"^final\s+class\s", rule="Declare classes final unless they are designed for extension."),
        FileMarker(id="pest-style", glob="tests/**/*Test.php", has=r"(^|\n)\s*(it|test)\(",
                   rule="Write tests in Pest closure style (it()/test()), not PHPUnit classes."),
        AbsentMarker(id="php-debug", glob=G, bad=r"\b(dd|dump|var_dump|print_r)\(",
                     rule="Do not commit debug output (dd/dump/var_dump/print_r)."),
        AbsentMarker(id="php-eval", glob=G, bad=r"\b(eval|extract)\s*\(",
                     rule="Do not use eval() or extract()."),
        AbsentMarker(id="php-error-suppress", glob=G, bad=r"(?:^|[^\w$@])@\$?[a-z_]+\(",
                     rule="Do not suppress errors with the @ operator; handle them."),
        AbsentMarker(id="php-array-fn", glob=G, bad=r"\barray\s*\(",
                     rule="Use the short array syntax [] instead of array()."),
        AbsentMarker(id="php-superglobals", glob=G, bad=r"\$_(GET|POST|REQUEST|COOKIE)\b",
                     rule="Read request input through a request object, not $_GET/$_POST superglobals."),
    ),
)
