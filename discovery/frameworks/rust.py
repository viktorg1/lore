from ..markers import ChoiceMarker, FileMarker, Option
from .base import Framework

AXUM = Framework(
    name="Axum", languages=("rust",), deps=("axum",),
    markers=(
        ChoiceMarker(id="axum-shared-state", glob="**/*.rs", min_applicable=5, options=(
            Option("State<T>", r"\bState<", "Share application state with the State<T> extractor."),
            Option("Extension<T>", r"\bExtension<", "Share application state with the Extension<T> extractor."))),
        FileMarker(id="axum-into-response", glob="**/*.rs", when=r"use\s+axum", min_applicable=3, has=r"impl\s+IntoResponse\s+for",
                   rule="Implement IntoResponse for error types so handlers can return Result<T, AppError>."),
        ChoiceMarker(id="axum-json", glob="**/*.rs", min_applicable=5, options=(
            Option("Json<T> extractor", r"\bJson<", "Accept and return JSON through axum::Json<T>."),
            Option("manual serde_json", r"serde_json::(?:from|to)_(?:str|slice|string|vec)\("))),
    ),
)
FRAMEWORKS = [AXUM]
