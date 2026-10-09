from ..markers import AbsentMarker, FileMarker, OccurrenceMarker
from .base import Framework

RAILS = Framework(
    name="Rails", languages=("ruby",), deps=("rails",),
    markers=(
        FileMarker(id="rails-strong-params", glob="app/controllers/**/*.rb", when=r"def\s+(?:create|update)\b", has=r"params\.(?:require|permit|expect)",
                   rule="Use strong parameters (params.require(...).permit(...)) in create/update actions."),
        AbsentMarker(id="rails-callbacks", glob="app/models/**/*.rb", bad=r"^\s*(?:before|after|around)_(?:save|create|update|destroy|validation|commit)\b",
                     rule="Avoid ActiveRecord callbacks; put side effects in service objects or jobs."),
        AbsentMarker(id="rails-default-scope", glob="app/models/**/*.rb", bad=r"\bdefault_scope\b", rule="Do not use default_scope."),
        AbsentMarker(id="rails-sql-interpolation", glob="app/**/*.rb", bad=r"where\(\s*[\"'][^\"'\n]*#\{",
                     rule="Never interpolate values into SQL strings; use placeholders or hash conditions."),
        OccurrenceMarker(id="rails-dependent", glob="app/models/**/*.rb", min_applicable=5,
                         total=r"^\s*(?:has_many|has_one)\s+:\w+", has=r"^\s*(?:has_many|has_one)\s+:\w+[^\n]*\bdependent:",
                         rule="Declare dependent: on every has_many/has_one association."),
    ),
)
FRAMEWORKS = [RAILS]
