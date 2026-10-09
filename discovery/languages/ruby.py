from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Language

G = "**/*.rb"
LANGUAGE = Language(
    name="ruby", extensions=("rb",), check_quotes=True,
    markers=(
        FileMarker(id="rb-frozen-string", glob=G, has=r"frozen_string_literal:\s*true",
                   rule="Start Ruby files with `# frozen_string_literal: true`."),
        AbsentMarker(id="rb-debugger", glob=G, bad=r"binding\.pry|byebug|\bdebugger\b", rule="Do not commit debugger statements."),
        AbsentMarker(id="rb-puts", glob=G, bad=r"^\s*(?:puts|pp)\b", rule="Use a logger, not puts/pp, in application code."),
        AbsentMarker(id="rb-rescue-exception", glob=G, bad=r"rescue\s+Exception\b", rule="Do not rescue Exception; rescue StandardError or something narrower."),
        AbsentMarker(id="rb-bare-rescue", glob=G, bad=r"^\s*rescue\s*$", rule="Never use a bare `rescue`; name the exception classes."),
        ChoiceMarker(id="rb-hash-syntax", glob=G, options=(
            Option("key: value", r"\b\w+:\s+[\w:\"'\[{@(]", "Use the modern hash syntax ({key: value})."),
            Option("hash rockets", r":\w+\s*=>", "Use hash rockets ({:key => value}); do not mix in key: value."))),
    ),
)
