"""Template-based pattern matching for command parsing.

Converts patterns like "[add|put] $item [to|on] the [grocery|shopping] list"
into compiled regex, matches against input text, and returns extracted fields.

Syntax:
    [alt1|alt2|alt3]  — matches any of the alternatives
    $name             — captures text into a named field (non-greedy)
    literal text      — matches literally (case-insensitive, flexible whitespace)

The same $name can appear in different alternatives of a [...] group.

Examples:
    >>> p = TemplatePattern("[add|put] $item [to|on] the list")
    >>> p.match("add ketchup to the list")
    {'item': 'ketchup'}
    >>> p.match("put diet 7 up on the list")
    {'item': 'diet 7 up'}
"""

import re


class TemplatePattern:
    """A compiled template pattern that can match text and extract named fields."""

    def __init__(self, template, greedy=False):
        self.template = template
        self._regex, self._group_map = _compile(template, greedy)

    def match(self, text):
        """Match text against this pattern. Returns dict of fields or None."""
        m = self._regex.match(text.strip().rstrip("?!.,"))
        if m is None:
            return None
        result = {}
        for group_num, field_name in self._group_map.items():
            value = m.group(group_num)
            if value is not None:
                result[field_name] = value.strip()
        return result

    def __repr__(self):
        return f"TemplatePattern({self.template!r})"


def template_match(template, text, greedy=False):
    """One-shot match: compile template and match text. Returns dict or None."""
    return TemplatePattern(template, greedy).match(text)


def match_any(templates, text):
    """Try matching text against a list of (template_or_TemplatePattern, tag) pairs.

    Returns (tag, fields_dict) for the first match, or None.
    Useful for classifying input against multiple patterns.
    """
    for tmpl, tag in templates:
        if isinstance(tmpl, str):
            result = template_match(tmpl, text)
        else:
            result = tmpl.match(text)
        if result is not None:
            return tag, result
    return None


# --- Compilation internals ---

class _Compiler:
    """Stateful compiler that tracks capturing group numbers."""

    def __init__(self, greedy=False):
        self.greedy = greedy
        self.group_count = 0
        self.group_map = {}  # group_number -> field_name

    def compile_template(self, template):
        """Compile a full template string. Returns (regex_str, group_map)."""
        regex_str = self._compile_fragment(template)
        pattern = '^' + regex_str + '$'
        return pattern, self.group_map

    def _compile_fragment(self, fragment):
        """Compile a fragment to a regex string."""
        parts = []
        i = 0
        s = fragment
        while i < len(s):
            if s[i] == '[':
                depth = 1
                j = i + 1
                while j < len(s) and depth > 0:
                    if s[j] == '[':
                        depth += 1
                    elif s[j] == ']':
                        depth -= 1
                    j += 1
                inner = s[i+1:j-1]
                alts = _split_alternatives(inner)
                alt_patterns = [self._compile_fragment(alt) for alt in alts]
                parts.append('(?:' + '|'.join(alt_patterns) + ')')
                i = j
            elif s[i] == '$':
                m = re.match(r'\$([a-zA-Z_]\w*)', s[i:])
                if m:
                    name = m.group(1)
                    self.group_count += 1
                    self.group_map[self.group_count] = name
                    capture = '.+' if self.greedy else '.+?'
                    parts.append(f'({capture})')
                    i += m.end()
                else:
                    parts.append(re.escape(s[i]))
                    i += 1
            else:
                if s[i] in ' \t':
                    while i < len(s) and s[i] in ' \t':
                        i += 1
                    parts.append(r'\s+')
                else:
                    parts.append(re.escape(s[i]))
                    i += 1
        return ''.join(parts)


def _split_alternatives(text):
    """Split on top-level | characters, respecting nested brackets."""
    alts = []
    depth = 0
    current = []
    for ch in text:
        if ch == '[':
            depth += 1
            current.append(ch)
        elif ch == ']':
            depth -= 1
            current.append(ch)
        elif ch == '|' and depth == 0:
            alts.append(''.join(current))
            current = []
        else:
            current.append(ch)
    alts.append(''.join(current))
    return alts


def _compile(template, greedy=False):
    """Compile a template string to a (compiled_regex, group_map) tuple."""
    compiler = _Compiler(greedy)
    pattern_str, group_map = compiler.compile_template(template)
    return re.compile(pattern_str, re.IGNORECASE), group_map


# --- Standalone tests ---

if __name__ == "__main__":
    passed = 0
    failed = 0

    def check(label, got, expected):
        global passed, failed
        if got == expected:
            passed += 1
            print(f"  PASS: {label}")
        else:
            failed += 1
            print(f"  FAIL: {label}")
            print(f"        expected: {expected}")
            print(f"        got:      {got}")

    print("=== TemplatePattern tests ===\n")

    # Basic field extraction
    p = TemplatePattern("the $object in $location")
    check("basic fields",
          p.match("the rain in Spain"),
          {"object": "rain", "location": "Spain"})

    # No match
    check("no match",
          p.match("a cat on a mat"),
          None)

    # Alternatives
    p = TemplatePattern("[add|put] $item [to|on] the list")
    check("alt: add...to",
          p.match("add ketchup to the list"),
          {"item": "ketchup"})
    check("alt: put...on",
          p.match("put mustard on the list"),
          {"item": "mustard"})
    check("alt: no match",
          p.match("remove ketchup from the list"),
          None)

    # Multi-word capture
    check("multi-word field",
          p.match("add diet 7 up to the list"),
          {"item": "diet 7 up"})

    # Case insensitive
    check("case insensitive",
          p.match("ADD Ketchup TO the list"),
          {"item": "Ketchup"})

    # Multiple alternatives in one pattern
    p = TemplatePattern("[add|put] $item [to|on] [the|my] [grocery|shopping] list")
    check("multi-alt: add...to the grocery list",
          p.match("add eggs to the grocery list"),
          {"item": "eggs"})
    check("multi-alt: put...on my shopping list",
          p.match("put milk on my shopping list"),
          {"item": "milk"})

    # Pattern with no fields (just matching)
    p = TemplatePattern("[say that again|repeat that|what did you say]")
    check("no fields: match",
          p.match("say that again"),
          {})
    check("no fields: alt match",
          p.match("repeat that"),
          {})
    check("no fields: no match",
          p.match("hello"),
          None)

    # Greedy capture
    p = TemplatePattern("remind me to $task at $time", greedy=True)
    check("greedy capture",
          p.match("remind me to feed the cat and the dog at 3pm"),
          {"task": "feed the cat and the dog", "time": "3pm"})

    # One-shot helper
    check("template_match helper",
          template_match("[hello|hi|hey] $name", "hello world"),
          {"name": "world"})

    # match_any helper
    patterns = [
        ("[add|put] $item [to|on] the list", "add"),
        ("[remove|take] $item [from|off] the list", "remove"),
        ("how many [items|things] [on|in] the list", "count"),
    ]
    result = match_any(patterns, "add milk to the list")
    check("match_any: add",
          result,
          ("add", {"item": "milk"}))
    result = match_any(patterns, "remove bread from the list")
    check("match_any: remove",
          result,
          ("remove", {"item": "bread"}))
    result = match_any(patterns, "how many items on the list")
    check("match_any: count",
          result,
          ("count", {}))
    result = match_any(patterns, "hello there")
    check("match_any: no match",
          result,
          None)

    # Flexible whitespace
    p = TemplatePattern("what time is it")
    check("flexible whitespace",
          p.match("what  time  is  it"),
          {})

    # With pre-compiled TemplatePattern in match_any
    patterns2 = [
        (TemplatePattern("[hello|hi]"), "greet"),
        (TemplatePattern("$thing is $adj"), "describe"),
    ]
    result = match_any(patterns2, "hi")
    check("match_any with TemplatePattern: greet",
          result,
          ("greet", {}))
    result = match_any(patterns2, "sky is blue")
    check("match_any with TemplatePattern: describe",
          result,
          ("describe", {"thing": "sky", "adj": "blue"}))

    # Field inside alternatives (same $name in different branches)
    p = TemplatePattern("[set a timer for $duration|set a $duration timer]")
    check("field in alt 1",
          p.match("set a timer for 5 minutes"),
          {"duration": "5 minutes"})
    check("field in alt 2",
          p.match("set a 5 minute timer"),
          {"duration": "5 minute"})

    # Partial match (should not match — anchored)
    p = TemplatePattern("hello")
    check("no partial match",
          p.match("hello world"),
          None)

    # Special regex characters in literal text
    p = TemplatePattern("what's the $thing")
    check("apostrophe in literal",
          p.match("what's the weather"),
          {"thing": "weather"})

    # Nested alternatives
    p = TemplatePattern("[good [morning|afternoon|evening]|hello|hi]")
    check("nested alt: good morning",
          p.match("good morning"),
          {})
    check("nested alt: good evening",
          p.match("good evening"),
          {})
    check("nested alt: hello",
          p.match("hello"),
          {})

    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests")
