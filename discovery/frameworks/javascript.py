from ..markers import AbsentMarker, ChoiceMarker, FileMarker, Option
from .base import Framework

REACT_FILES = "**/*.{jsx,tsx}"
REACT = Framework(
    name="React", languages=("javascript", "typescript"), deps=("react",),
    markers=(
        ChoiceMarker(id="react-component-kind", glob=REACT_FILES, options=(
            Option("function components",
                   r"(?:^|\s)function\s+[A-Z]\w*\s*\(|^(?:export\s+)?const\s+[A-Z]\w*(?::[^=\n]+)?\s*=\s*(?:React\.)?(?:memo\(|forwardRef\(|async\s*)?\(?[^)\n]*\)?\s*(?::[^=\n]+)?=>",
                   "Write function components with hooks; do not write class components."),
            Option("class components", r"class\s+\w+\s+extends\s+(?:React\.)?(?:Pure)?Component\b",
                   "Write class components (extends React.Component)."))),
        ChoiceMarker(id="react-component-declaration", glob=REACT_FILES, options=(
            Option("function declarations", r"^(?:export\s+(?:default\s+)?)?function\s+[A-Z]\w*\s*\(",
                   "Declare components with function declarations (function Foo() {})."),
            Option("arrow components", r"^(?:export\s+)?const\s+[A-Z]\w*(?::[^=\n]+)?\s*=\s*(?:React\.)?(?:memo\(|forwardRef\(|async\s*)?\(?[^)\n]*\)?\s*(?::[^=\n]+)?=>",
                   "Declare components as const arrow functions."))),
        ChoiceMarker(id="react-props-typing", glob="**/*.tsx", options=(
            Option("interface Props", r"interface\s+\w*Props\b", "Type component props with `interface FooProps`."),
            Option("type Props", r"type\s+\w*Props\s*=", "Type component props with `type FooProps = {...}`."))),
        ChoiceMarker(id="react-styling", glob=REACT_FILES, options=(
            Option("CSS Modules", r"from\s+['\"][^'\"]+\.module\.(?:css|scss|sass)['\"]", "Style components with CSS Modules."),
            Option("styled-components", r"\bstyled(?:\.\w+|\()", "Style components with styled-components / CSS-in-JS."))),
        AbsentMarker(id="react-dangerous-html", glob=REACT_FILES, bad=r"dangerouslySetInnerHTML",
                     rule="Do not use dangerouslySetInnerHTML (XSS risk)."),
        AbsentMarker(id="react-index-key", glob=REACT_FILES, bad=r"\bkey=\{\s*(?:i|idx|index)\s*\}",
                     rule="Do not use the array index as a React key."),
        AbsentMarker(id="react-default-props", glob=REACT_FILES, bad=r"\.defaultProps\s*=",
                     rule="Use default parameter values instead of defaultProps."),
        AbsentMarker(id="react-direct-dom", glob=REACT_FILES, bad=r"document\.(?:getElementById|querySelector)",
                     rule="Do not query the DOM directly in components; use refs and state."),
        FileMarker(id="react-testing-library", glob="**/*.{test,spec}.{jsx,tsx,js,ts}", when=r"\brender\(", has=r"@testing-library/react",
                   rule="Test components with React Testing Library."),
    ),
)

EXPRESS_FILES = "**/*.{js,mjs,cjs,ts}"
EXPRESS = Framework(
    name="Express", languages=("javascript", "typescript"), deps=("express",),
    markers=(
        ChoiceMarker(id="express-routing", glob=EXPRESS_FILES, options=(
            Option("express.Router modules", r"\b(?:express\.)?Router\(\)", "Define routes on express.Router() modules and mount them with app.use()."),
            Option("routes on app", r"\bapp\.(?:get|post|put|patch|delete)\(", "Define routes directly on the app instance."))),
        ChoiceMarker(id="express-responses", glob=EXPRESS_FILES, options=(
            Option("res.json", r"\bres\.json\(", "Respond to API calls with res.json()."),
            Option("res.send", r"\bres\.send\(", "Respond with res.send()."))),
        AbsentMarker(id="express-body-parser", glob=EXPRESS_FILES, bad=r"body-?parser",
                     rule="Use the built-in express.json()/express.urlencoded(), not the body-parser package."),
        FileMarker(id="express-helmet", glob=EXPRESS_FILES, when=r"\bexpress\(\)", min_applicable=1, has=r"helmet",
                   rule="Apply the helmet security-headers middleware on the app."),
        ChoiceMarker(id="express-handler-style", glob=EXPRESS_FILES, options=(
            Option("async handlers", r"\b(?:get|post|put|patch|delete|use)\(\s*[^)\n]*async\s*\(", "Write route handlers as async functions."),
            Option("callback handlers", r"\b(?:get|post|put|patch|delete)\(\s*['\"/][^)\n]*,\s*(?:function\s*)?\(\s*req\b", "Write route handlers as synchronous callbacks."))),
    ),
)
FRAMEWORKS = [REACT, EXPRESS]
