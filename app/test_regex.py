import re

MEMORY_LINE_RE = re.compile(r"^-\s+(?:\[([^\]]*)\]\s+)?(.+)$")

content = "- [self_correction] [auto-corrección] Al responder 'Mi usuario en Github es sebadp recuerdalo por favor...', los guardrails detectaron: no_pii. Recordar evitar este tipo de error."

m = MEMORY_LINE_RE.match(content)
if m:
    print("Match!")
    print("Category:", m.group(1))
    print("Content:", m.group(2))
else:
    print("No match")
