from ..markers import ChoiceMarker, Option
from .base import Framework

SVELTEKIT = Framework(
    name="SvelteKit", languages=("svelte", "typescript", "javascript"), deps=("@sveltejs/kit",),
    markers=(
        ChoiceMarker(id="sveltekit-page-state", glob="**/*.{svelte,ts,js}", min_applicable=3, options=(
            Option("$app/state", r"from\s+['\"]\$app/state['\"]", "Read page/navigation state from $app/state."),
            Option("$app/stores", r"from\s+['\"]\$app/stores['\"]", "Read page/navigation state from $app/stores."))),
        ChoiceMarker(id="sveltekit-lib-alias", glob="**/*.{svelte,ts,js}", options=(
            Option("$lib alias", r"from\s+['\"]\$lib/", "Import shared code through the $lib alias."),
            Option("deep relative", r"from\s+['\"](?:\.\./){2,}"))),
    ),
)
FRAMEWORKS = [SVELTEKIT]
