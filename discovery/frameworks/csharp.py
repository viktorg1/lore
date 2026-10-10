from ..markers import ChoiceMarker, FileMarker, OccurrenceMarker, Option
from .base import Framework

ASPNET = Framework(
    name="ASP.NET Core", languages=("csharp",),
    deps=("microsoft.net.sdk.web", "microsoft.aspnetcore.app", "microsoft.aspnetcore.mvc.testing"),
    signatures=(r"WebApplication\.CreateBuilder",), signature_files=1,
    markers=(
        ChoiceMarker(id="aspnet-api-style", glob="**/*.cs", options=(
            Option("controllers", r"\[ApiController\]", "Build APIs with [ApiController] controllers."),
            Option("minimal APIs", r"\b(?:app|endpoints|group)\.Map(?:Get|Post|Put|Delete|Patch)\(", "Build APIs with minimal-API endpoints (app.MapGet/MapPost)."))),
        FileMarker(id="aspnet-api-controller-attr", glob="**/Controllers/**/*.cs", when=r":\s*(?:Controller|ControllerBase)\b", has=r"\[ApiController\]",
                   rule="Mark API controllers with [ApiController]."),
        OccurrenceMarker(id="aspnet-async-actions", glob="**/Controllers/**/*.cs",
                         total=r"public\s+(?:virtual\s+)?(?:async\s+)?(?:Task<)?(?:ActionResult|IActionResult)",
                         has=r"public\s+(?:virtual\s+)?async\s+Task<", min_applicable=5,
                         rule="Make controller actions async (async Task<IActionResult>)."),
        ChoiceMarker(id="aspnet-action-results", glob="**/Controllers/**/*.cs", options=(
            Option("ActionResult<T>", r"\bActionResult<", "Return ActionResult<T> from controller actions."),
            Option("IActionResult", r"\bIActionResult\b", "Return IActionResult from controller actions."))),
        FileMarker(id="aspnet-controller-logging", glob="**/Controllers/**/*.cs", when=r":\s*(?:Controller|ControllerBase)\b", has=r"ILogger<",
                   rule="Inject ILogger<T> into controllers."),
    ),
)
FRAMEWORKS = [ASPNET]
