from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Language

G = "**/*.svelte"
LANGUAGE = Language(
    name="svelte", extensions=("svelte",), check_semicolons=True,
    markers=(
        FileMarker(id="svelte-ts", glob=G, when=r"<script", has=r"<script[^>]*lang=[\"']ts[\"']",
                   rule="Use TypeScript in Svelte components (<script lang=\"ts\">)."),
        ChoiceMarker(id="svelte-runes", glob=G, options=(
            Option("Svelte 5 runes", r"\$(?:state|derived|effect|props)\b", "Use Svelte 5 runes ($state/$derived/$props), not legacy reactive syntax."),
            Option("legacy syntax", r"^\s*export\s+let\s|^\s*\$:\s", "Use Svelte 4 syntax (export let, $:); do not mix in runes."))),
        AbsentMarker(id="svelte-html", glob=G, bad=r"\{@html\b", rule="Do not use {@html} (XSS risk); render text or sanitize first."),
    ),
)
