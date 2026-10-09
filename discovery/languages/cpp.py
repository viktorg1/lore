from ..markers import AbsentMarker, ChoiceMarker, Option
from .base import Language

G = "**/*.{cpp,cc,cxx,hpp}"
LANGUAGE = Language(
    name="cpp", extensions=("cpp", "hpp", "cc", "cxx"),
    markers=(
        AbsentMarker(id="cpp-raw-new", glob=G, bad=r"\bnew\s+[A-Za-z_]|\bdelete\s*(?:\[\])?\s+\w", rule="Avoid raw new/delete; use smart pointers and containers."),
        AbsentMarker(id="cpp-using-namespace-std", glob=G, bad=r"using\s+namespace\s+std\s*;", rule="Do not write `using namespace std`."),
        AbsentMarker(id="cpp-null", glob=G, bad=r"\bNULL\b", rule="Use nullptr, not NULL."),
        AbsentMarker(id="cpp-endl", glob=G, bad=r"std::endl", rule="Use '\\n', not std::endl."),
        ChoiceMarker(id="cpp-include-guards", glob="**/*.hpp", options=(
            Option("#pragma once", r"^#pragma once", "Guard headers with #pragma once."),
            Option("#ifndef guards", r"^#ifndef\s+\w+_H\w*", "Guard headers with #ifndef/#define include guards."))),
    ),
)
