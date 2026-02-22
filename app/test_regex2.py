import re

MEMORY_LINE_RE = re.compile(r"^-\s+(?:\[([^\]]*)\]\s+)?(.+)$")

content = "- [auto-corrección] Al responder 'Mi usuario en Github es sebadp...'"

m = MEMORY_LINE_RE.match(content)
if m:
    print("Match!")
    print("Category:", repr(m.group(1)))
    print("Content:", repr(m.group(2)))
else:
    print("No match")
