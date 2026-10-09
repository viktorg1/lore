from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Framework

LARAVEL = Framework(
    name="Laravel", languages=("php",), deps=("laravel/framework",),
    markers=(
        ChoiceMarker(id="laravel-validation", glob="app/Http/Controllers/**/*.php", options=(
            Option("inline validate()", r"->validate\(", "Validate request input inline with $request->validate([...]) in controllers."),
            Option("Form Requests", r"use\s+App\\Http\\Requests\\", "Validate controller input with dedicated Form Request classes, not inline."))),
        FileMarker(id="laravel-fillable", glob="app/Models/**/*.php", has=r"\$fillable|\$guarded",
                   rule="Declare $fillable (or $guarded) explicitly on every Eloquent model."),
        FileMarker(id="laravel-has-factory", glob="app/Models/**/*.php", when=r"extends\s+(?:Model|Authenticatable)", has=r"use\s+HasFactory",
                   rule="Add the HasFactory trait to Eloquent models."),
        AbsentMarker(id="laravel-raw-sql", glob="app/**/*.php", bad=r"DB::(?:raw|select|statement|unprepared)\(|whereRaw\(|selectRaw\(",
                     rule="Use Eloquent / the query builder instead of raw SQL."),
        AbsentMarker(id="laravel-env-outside-config", glob="app/**/*.php", bad=r"\benv\(",
                     rule="Do not call env() outside config files; read values with config()."),
        AbsentMarker(id="laravel-route-closures", glob="routes/**/*.php", min_applicable=1,
                     bad=r"Route::\w+\([^,\n]+,\s*(?:static\s+)?(?:function|fn)\b",
                     rule="Route to controller methods, not closures."),
    ),
)
FRAMEWORKS = [LARAVEL]
