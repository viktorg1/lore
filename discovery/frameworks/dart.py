from ..markers import ChoiceMarker, FileMarker, Option
from .base import Framework

FLUTTER = Framework(
    name="Flutter", languages=("dart",), deps=("flutter",),
    markers=(
        ChoiceMarker(id="flutter-widget-kind", glob="**/*.dart", options=(
            Option("StatelessWidget", r"extends\s+StatelessWidget\b", "Build widgets as StatelessWidget unless they own local state."),
            Option("StatefulWidget", r"extends\s+StatefulWidget\b"))),
        ChoiceMarker(id="flutter-state-management", glob="**/*.dart", min_applicable=5, options=(
            Option("Riverpod", r"package:(?:flutter_)?riverpod", "Manage state with Riverpod providers."),
            Option("Provider", r"package:provider/", "Manage state with Provider."),
            Option("BLoC", r"package:(?:flutter_)?bloc/", "Manage state with BLoC/Cubit."),
            Option("GetX", r"package:get/", "Manage state with GetX."))),
        FileMarker(id="flutter-const-widgets", glob="**/*.dart", when=r"extends\s+StatelessWidget", min_applicable=5,
                   has=r"\bconst\s+[A-Z]\w*\(\{?", rule="Give stateless widgets const constructors."),
        ChoiceMarker(id="flutter-key-style", glob="**/*.dart", min_applicable=5, options=(
            Option("super.key", r"\bsuper\.key\b", "Forward keys with `super.key`."),
            Option("Key? key", r"\bKey\??\s+key\b", "Forward keys with `Key? key` and `super(key: key)`."))),
    ),
)
FRAMEWORKS = [FLUTTER]
