from ..markers import AbsentMarker, ChoiceMarker, FileMarker, OccurrenceMarker, Option
from .base import Language

G = "**/*.vue"
LANGUAGE = Language(
    name="vue", extensions=("vue",), check_semicolons=True,
    markers=(
        FileMarker(id="vue-script-setup", glob=G, when=r"<script", has=r"<script\s+setup",
                   rule="Write Vue components with <script setup>."),
        FileMarker(id="vue-ts", glob=G, when=r"<script", has=r"<script[^>]*lang=[\"']ts[\"']",
                   rule="Use TypeScript in Vue components (<script setup lang=\"ts\">)."),
        FileMarker(id="vue-scoped-style", glob=G, when=r"<style", has=r"<style[^>]*\bscoped\b",
                   rule="Scope component styles with <style scoped>."),
        OccurrenceMarker(id="vue-v-for-key", glob=G, total=r"\bv-for=", has=r"\bv-for=\"[^\"]*\"[^>]*:key=|:key=\"[^\"]*\"[^>]*\bv-for=",
                         rule="Always bind a :key on v-for elements."),
        AbsentMarker(id="vue-v-html", glob=G, bad=r"\bv-html\b", rule="Do not use v-html (XSS risk); render text or sanitize first."),
        ChoiceMarker(id="vue-props-declaration", glob=G, options=(
            Option("type-based defineProps", r"defineProps<", "Declare props with the type-based defineProps<...>() form."),
            Option("runtime defineProps", r"defineProps\(\s*[\{\[]", "Declare props with the runtime defineProps({...}) form."))),
        ChoiceMarker(id="vue-emits-declaration", glob=G, options=(
            Option("type-based defineEmits", r"defineEmits<", "Declare emits with the type-based defineEmits<...>() form."),
            Option("runtime defineEmits", r"defineEmits\(\s*[\[\{]", "Declare emits with the runtime defineEmits([...]) form."))),
        ChoiceMarker(id="vue-component-tags", glob=G, options=(
            Option("PascalCase tags", r"<[A-Z][A-Za-z0-9]+[\s/>]", "Use PascalCase component tags in templates (<MyButton />)."),
            Option("kebab-case tags", r"<[a-z]+(?:-[a-z0-9]+)+[\s/>]", "Use kebab-case component tags in templates (<my-button>)."))),
        ChoiceMarker(id="vue-reactivity", glob=G, options=(
            Option("ref()", r"\bref\(", "Prefer ref() over reactive() for component state."),
            Option("reactive()", r"\breactive\(", "Prefer reactive() objects over ref() for component state."))),
    ),
)
