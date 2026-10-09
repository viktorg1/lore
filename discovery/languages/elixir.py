from ..markers import AbsentMarker, FileMarker, OccurrenceMarker
from .base import Language

G = "**/*.{ex,exs}"
LANGUAGE = Language(
    name="elixir", extensions=("ex", "exs"), formatter_enforced=True,
    markers=(
        AbsentMarker(id="ex-io-inspect", glob=G, bad=r"IO\.inspect\(", rule="Remove IO.inspect debugging; use Logger."),
        AbsentMarker(id="ex-io-puts", glob=G, bad=r"IO\.puts\(", rule="Use Logger, not IO.puts."),
        FileMarker(id="ex-moduledoc", glob="lib/**/*.ex", when=r"^defmodule\s", has=r"@moduledoc",
                   rule="Give every module an @moduledoc."),
        OccurrenceMarker(id="ex-specs", glob="lib/**/*.ex",
                         total=r"^\s*def\s+\w+", has=r"@spec[^\n]*\n(?:\s*@[^\n]*\n)*\s*def\s+\w+",
                         rule="Add an @spec to every public function."),
    ),
)
