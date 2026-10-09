from ..markers import AbsentMarker, ChoiceMarker, OccurrenceMarker, Option
from .base import Framework

JVM = "**/*.{java,kt}"
SPRING = Framework(
    name="Spring Boot", languages=("java", "kotlin"),
    deps=("spring-boot-starter", "spring-boot-starter-web", "spring-boot-starter-webflux", "org.springframework.boot", "spring-boot"),
    markers=(
        ChoiceMarker(id="spring-injection", glob=JVM, options=(
            Option("constructor injection", r"@RequiredArgsConstructor|^\s*private\s+final\s+\w+(?:<[^>]+>)?\s+\w+;",
                   "Inject dependencies through the constructor (final fields / @RequiredArgsConstructor), not field @Autowired."),
            Option("field @Autowired", r"@Autowired\s*\n?\s*(?:private|protected|public)?\s*[\w<>]+\s+\w+\s*;",
                   "Dependencies are injected into fields with @Autowired; match that style."))),
        ChoiceMarker(id="spring-controllers", glob=JVM, options=(
            Option("@RestController", r"@RestController\b", "Annotate API controllers with @RestController."),
            Option("@Controller", r"@Controller\b", "Annotate controllers with @Controller (+ @ResponseBody where needed)."))),
        ChoiceMarker(id="spring-dtos", glob=JVM, options=(
            Option("records", r"\brecord\s+\w+\s*\(", "Use Java records for DTOs."),
            Option("Lombok @Data", r"@Data\b", "Use Lombok @Data classes for DTOs."))),
        OccurrenceMarker(id="spring-valid-body", glob=JVM, total=r"@RequestBody\b", has=r"@Valid(?:ated)?\s+@RequestBody|@RequestBody\s+@Valid(?:ated)?",
                         min_applicable=5, rule="Validate request bodies with @Valid on every @RequestBody."),
        ChoiceMarker(id="spring-logging", glob=JVM, options=(
            Option("@Slf4j", r"@Slf4j\b", "Log through Lombok's @Slf4j logger."),
            Option("LoggerFactory", r"LoggerFactory\.getLogger", "Create loggers with LoggerFactory.getLogger(...)."))),
        ChoiceMarker(id="spring-mappings", glob=JVM, options=(
            Option("@GetMapping & co", r"@(?:Get|Post|Put|Delete|Patch)Mapping\b", "Use @GetMapping/@PostMapping shortcuts."),
            Option("@RequestMapping(method=)", r"@RequestMapping\([^)]*method\s*=", "Declare HTTP methods with @RequestMapping(method = ...)."))),
    ),
)
KTOR = Framework(
    name="Ktor", languages=("kotlin",), deps=("ktor-server-core", "ktor-server-netty", "io.ktor"),
    markers=(
        ChoiceMarker(id="ktor-serialization", glob="**/*.kt", options=(
            Option("kotlinx.serialization", r"kotlinx\.serialization", "Serialize with kotlinx.serialization (@Serializable)."),
            Option("Jackson", r"com\.fasterxml\.jackson", "Serialize with Jackson."),
            Option("Gson", r"com\.google\.gson", "Serialize with Gson."))),
        AbsentMarker(id="ktor-run-blocking", glob="**/*.kt", bad=r"\brunBlocking\b", rule="Do not use runBlocking in server code; stay suspending."),
        ChoiceMarker(id="ktor-routing-organisation", glob="**/*.kt", min_applicable=3, options=(
            Option("Route extension functions", r"\bfun\s+Route\.\w+\(", "Define routes as `fun Route.xxxRoutes()` extension functions."),
            Option("inline routing blocks", r"\brouting\s*\{\s*\n"))),
    ),
)
FRAMEWORKS = [SPRING, KTOR]
