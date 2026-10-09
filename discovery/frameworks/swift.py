from ..markers import AbsentMarker, ChoiceMarker, Option
from .base import Framework

SWIFTUI = Framework(
    name="SwiftUI", languages=("swift",), signatures=(r"^import\s+SwiftUI",), signature_files=3,
    markers=(
        ChoiceMarker(id="swiftui-observation", glob="**/*.swift", options=(
            Option("@Observable", r"@Observable\b", "Model state with the @Observable macro."),
            Option("ObservableObject", r"\bObservableObject\b|@StateObject|@ObservedObject", "Model state with ObservableObject / @Published."))),
        ChoiceMarker(id="swiftui-previews", glob="**/*.swift", options=(
            Option("#Preview", r"^#Preview\b", "Write previews with the #Preview macro."),
            Option("PreviewProvider", r"PreviewProvider\b", "Write previews as PreviewProvider structs."))),
        ChoiceMarker(id="swiftui-navigation", glob="**/*.swift", min_applicable=3, options=(
            Option("NavigationStack", r"\bNavigationStack\b", "Navigate with NavigationStack."),
            Option("NavigationView", r"\bNavigationView\b"))),
        AbsentMarker(id="swiftui-any-view", glob="**/*.swift", bad=r"\bAnyView\b", rule="Avoid AnyView; use @ViewBuilder or generics."),
        AbsentMarker(id="swiftui-dispatch-main", glob="**/*.swift", bad=r"DispatchQueue\.main\.async",
                     rule="Use @MainActor / await MainActor.run, not DispatchQueue.main.async."),
    ),
)
FRAMEWORKS = [SWIFTUI]
