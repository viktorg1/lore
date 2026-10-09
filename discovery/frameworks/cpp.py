from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Framework

QT = Framework(
    name="Qt", languages=("cpp", "c"), deps=("qt", "qt4", "qt5", "qt6"), signatures=(r"#include\s*<Q\w+>",), signature_files=3,
    markers=(
        ChoiceMarker(id="qt-connect", glob="**/*.{cpp,cc,cxx,hpp,h}", min_applicable=5, options=(
            Option("pointer-to-member connect", r"connect\([^;]*&\w+::\w+", "Connect signals with the pointer-to-member syntax (&Class::signal)."),
            Option("SIGNAL/SLOT macros", r"\bSIGNAL\(|\bSLOT\(", "Connect signals with the SIGNAL()/SLOT() macros."))),
        FileMarker(id="qt-q-object", glob="**/*.{h,hpp}", when=r":\s*public\s+Q(?:Object|Widget|MainWindow|Dialog)\b", has=r"\bQ_OBJECT\b",
                   rule="Add Q_OBJECT to every QObject subclass."),
        AbsentMarker(id="qt-qdebug", glob="**/*.{cpp,cc,cxx,hpp,h}", bad=r"\bqDebug\(", rule="Remove qDebug() calls; use a logging category."),
    ),
)
FRAMEWORKS = [QT]
