from ..markers import AbsentMarker, ChoiceMarker, Option
from .base import Language

LANGUAGE = Language(
    name="c", extensions=("c", "h"),
    markers=(
        AbsentMarker(id="c-unsafe-libc", glob="**/*.{c,h}", bad=r"\b(?:gets|strcpy|strcat|sprintf)\s*\(",
                     rule="Do not use unbounded libc calls (gets/strcpy/strcat/sprintf); use bounded variants."),
        AbsentMarker(id="c-atoi", glob="**/*.{c,h}", bad=r"\b(?:atoi|atol|atof)\s*\(", rule="Use the strto* functions, not atoi/atol/atof."),
        ChoiceMarker(id="c-include-guards", glob="**/*.h", options=(
            Option("#pragma once", r"^#pragma once", "Guard headers with #pragma once."),
            Option("#ifndef guards", r"^#ifndef\s+\w+_H\w*", "Guard headers with #ifndef/#define include guards."))),
    ),
)
