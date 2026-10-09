from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Framework

SRC = "**/*.{vue,js,ts}"
VUE = Framework(
    name="Vue", languages=("vue", "javascript", "typescript"), deps=("vue",),
    markers=(
        ChoiceMarker(id="vue-state-management", glob=SRC, options=(
            Option("Pinia", r"from\s+['\"]pinia['\"]", "Share state with Pinia stores."),
            Option("Vuex", r"from\s+['\"]vuex['\"]", "Share state with Vuex."))),
        ChoiceMarker(id="vue-pinia-store-style", glob=SRC, options=(
            Option("setup stores", r"defineStore\(\s*['\"][^'\"]+['\"]\s*,\s*(?:async\s*)?\(\)\s*=>", "Define Pinia stores in setup style: defineStore('x', () => {...})."),
            Option("options stores", r"defineStore\(\s*['\"][^'\"]+['\"]\s*,\s*\{", "Define Pinia stores in options style: defineStore('x', { state, getters, actions })."))),
        FileMarker(id="vue-composables-naming", glob="**/composables/**/*.{ts,js}", min_applicable=3,
                   has=r"export\s+(?:default\s+)?(?:async\s+)?function\s+use[A-Z]|export\s+const\s+use[A-Z]",
                   rule="Name composables useXxx and keep them in composables/."),
        ChoiceMarker(id="vue-router-usage", glob=SRC, options=(
            Option("useRouter()", r"\buse(?:Router|Route)\(\)", "Navigate with useRouter()/useRoute() from vue-router."),
            Option("this.$router", r"this\.\$(?:router|route)\b", "Navigate with this.$router / this.$route."))),
        AbsentMarker(id="vue-vue2-api", glob=SRC, bad=r"\bnew\s+Vue\(|Vue\.extend\(|Vue\.component\(",
                     rule="Use the Vue 3 API (createApp, defineComponent), not new Vue()/Vue.extend()."),
    ),
)
FRAMEWORKS = [VUE]
