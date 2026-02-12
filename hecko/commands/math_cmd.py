"""Math and unit conversion command.

Handles:
    "what's 347 times 23"
    "what is 15% of 85"
    "what's the square root of 144"
    "how many tablespoons in a quarter cup"
    "how many feet in a mile"
    "convert 72 fahrenheit to celsius"
    "what's 5 plus 3"
"""

import math
import re

import pint

_ureg = pint.UnitRegistry()

# --- Fractional word numbers ---

_WORD_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100, "thousand": 1000, "million": 1e6,
    "a": 1, "an": 1,
}

_FRACTIONS = {
    "half": 0.5, "a half": 0.5, "one half": 0.5,
    "third": 1/3, "a third": 1/3, "one third": 1/3,
    "quarter": 0.25, "a quarter": 0.25, "one quarter": 0.25,
    "fourth": 0.25, "a fourth": 0.25, "one fourth": 0.25,
    "eighth": 0.125, "an eighth": 0.125, "one eighth": 0.125,
    "three quarters": 0.75, "three fourths": 0.75,
    "two thirds": 2/3,
}


def _parse_number(s):
    """Try to parse a number from text. Returns float or None."""
    s = s.strip().lower().rstrip(".")

    # Direct numeric
    try:
        return float(s.replace(",", ""))
    except ValueError:
        pass

    # Fractions like "a quarter", "one half"
    for phrase, val in _FRACTIONS.items():
        if s == phrase:
            return val

    # "N and a half" etc.
    m = re.match(r"(\d+(?:\.\d+)?)\s+and\s+(.+)", s)
    if m:
        frac = _FRACTIONS.get(m.group(2).strip())
        if frac is not None:
            return float(m.group(1)) + frac

    # Word numbers
    if s in _WORD_NUMS:
        return float(_WORD_NUMS[s])

    return None


# --- Unit aliases (Whisper-friendly) ---

_UNIT_ALIASES = {
    "fahrenheit": "degF", "degrees fahrenheit": "degF",
    "celsius": "degC", "degrees celsius": "degC", "centigrade": "degC",
    "tablespoons": "tablespoon", "tablespoon": "tablespoon", "tbsp": "tablespoon",
    "teaspoons": "teaspoon", "teaspoon": "teaspoon", "tsp": "teaspoon",
    "cups": "cup", "cup": "cup",
    "ounces": "ounce", "ounce": "ounce", "oz": "ounce",
    "fluid ounces": "fluid_ounce", "fluid ounce": "fluid_ounce",
    "pounds": "pound", "pound": "pound", "lbs": "pound",
    "grams": "gram", "gram": "gram",
    "kilograms": "kilogram", "kilogram": "kilogram", "kilos": "kilogram",
    "liters": "liter", "liter": "liter", "litres": "liter",
    "milliliters": "milliliter", "milliliter": "milliliter", "ml": "milliliter",
    "gallons": "gallon", "gallon": "gallon",
    "quarts": "quart", "quart": "quart",
    "pints": "pint", "pint": "pint",
    "inches": "inch", "inch": "inch",
    "feet": "foot", "foot": "foot",
    "yards": "yard", "yard": "yard",
    "miles": "mile", "mile": "mile",
    "meters": "meter", "meter": "meter", "metres": "meter",
    "centimeters": "centimeter", "centimeter": "centimeter", "cm": "centimeter",
    "millimeters": "millimeter", "millimeter": "millimeter", "mm": "millimeter",
    "kilometers": "kilometer", "kilometer": "kilometer", "km": "kilometer",
}


def _resolve_unit(s):
    """Resolve a unit string to a pint-compatible name."""
    s = s.strip().lower()
    return _UNIT_ALIASES.get(s, s)


def _is_temperature(unit_str):
    """Check if a unit is a temperature unit."""
    return unit_str in ("degF", "degC", "kelvin")


# --- Formatting ---

def _fmt_number(n):
    """Format a number nicely for speech."""
    if n == int(n) and abs(n) < 1e15:
        return f"{int(n):,}"
    # Check for clean fractions
    for label, val in [("a half", 0.5), ("a third", 1/3), ("two thirds", 2/3),
                       ("a quarter", 0.25), ("three quarters", 0.75),
                       ("an eighth", 0.125)]:
        if abs(n - val) < 1e-9:
            return label
    # Reasonable decimal
    if abs(n) >= 0.01:
        formatted = f"{n:,.4f}".rstrip("0").rstrip(".")
        return formatted
    return f"{n:g}"


_UNIT_SPEECH = {
    "tablespoon": ("tablespoon", "tablespoons"),
    "teaspoon": ("teaspoon", "teaspoons"),
    "cup": ("cup", "cups"),
    "ounce": ("ounce", "ounces"),
    "fluid_ounce": ("fluid ounce", "fluid ounces"),
    "pound": ("pound", "pounds"),
    "gram": ("gram", "grams"),
    "kilogram": ("kilogram", "kilograms"),
    "liter": ("liter", "liters"),
    "milliliter": ("milliliter", "milliliters"),
    "gallon": ("gallon", "gallons"),
    "quart": ("quart", "quarts"),
    "pint": ("pint", "pints"),
    "inch": ("inch", "inches"),
    "foot": ("foot", "feet"),
    "yard": ("yard", "yards"),
    "mile": ("mile", "miles"),
    "meter": ("meter", "meters"),
    "centimeter": ("centimeter", "centimeters"),
    "millimeter": ("millimeter", "millimeters"),
    "kilometer": ("kilometer", "kilometers"),
    "degF": ("degree Fahrenheit", "degrees Fahrenheit"),
    "degC": ("degree Celsius", "degrees Celsius"),
    "kelvin": ("kelvin", "kelvin"),
}


def _fmt_unit(unit, value):
    """Format a unit name for speech (singular/plural).

    Uses singular for values <= 1 (e.g., 'a quarter cup', 'a half gallon').
    """
    name = str(unit)
    plural = value > 1 + 1e-9
    if name in _UNIT_SPEECH:
        return _UNIT_SPEECH[name][1 if plural else 0]
    # Fallback
    name = name.replace("_", " ")
    if plural and not name.endswith("s"):
        name += "s"
    return name


# --- Unit conversion ---

def _try_unit_conversion(text):
    """Try to parse a unit conversion query. Returns response string or None."""
    t = text.lower().strip().rstrip("?.")

    # Pattern: "how many X in (a/an/N) Y"
    m = re.search(r"how\s+many\s+(\w[\w\s]*?)\s+(?:are\s+)?in\s+(.+)", t)
    if m:
        target_unit_raw = m.group(1).strip()
        source_raw = m.group(2).strip()
        return _do_conversion(source_raw, target_unit_raw)

    # Pattern: "convert N X to Y"
    m = re.search(r"convert\s+(.+?)\s+to\s+(\w[\w\s]*?)$", t)
    if m:
        source_raw = m.group(1).strip()
        target_unit_raw = m.group(2).strip()
        return _do_conversion(source_raw, target_unit_raw)

    # Pattern: "what is N X in Y"
    m = re.search(r"what(?:'s|\s+is)\s+(.+?)\s+in\s+(\w[\w\s]*?)$", t)
    if m:
        source_raw = m.group(1).strip()
        target_unit_raw = m.group(2).strip()
        return _do_conversion(source_raw, target_unit_raw)

    return None


def _do_conversion(source_raw, target_unit_raw):
    """Parse source quantity + unit and target unit, perform conversion."""
    target_unit = _resolve_unit(target_unit_raw)

    # Parse source: try to split into number + unit
    # "a quarter cup", "3 tablespoons", "72 fahrenheit", "a liter"
    source_val, source_unit = _split_quantity(source_raw)
    if source_val is None or source_unit is None:
        return None

    source_unit = _resolve_unit(source_unit)

    try:
        if _is_temperature(source_unit) or _is_temperature(target_unit):
            result = _ureg.Quantity(source_val, source_unit).to(target_unit)
        else:
            result = (_ureg.Quantity(source_val, source_unit)).to(target_unit)

        result_val = result.magnitude
        src_unit_name = _fmt_unit(source_unit, source_val)
        dst_unit_name = _fmt_unit(target_unit, result_val)
        if _is_temperature(source_unit) or _is_temperature(target_unit):
            return (f"{_fmt_number(source_val)} {src_unit_name} "
                    f"is {_fmt_number(result_val)} {dst_unit_name}.")
        return (f"There are {_fmt_number(result_val)} {dst_unit_name} "
                f"in {_fmt_number(source_val)} {src_unit_name}.")
    except Exception:
        return None


def _split_quantity(text):
    """Split 'a quarter cup' into (0.25, 'cup'). Returns (value, unit_str) or (None, None)."""
    t = text.strip().lower()

    # Try "N unit" where N is numeric
    m = re.match(r"([\d,]+(?:\.\d+)?)\s+(.+)", t)
    if m:
        val = _parse_number(m.group(1))
        if val is not None:
            return val, m.group(2).strip()

    # Try fraction words at the start: "a quarter cup", "a quarter of a cup"
    for phrase, val in sorted(_FRACTIONS.items(), key=lambda x: -len(x[0])):
        if t.startswith(phrase + " "):
            remainder = t[len(phrase):].strip()
            # Strip "of a" / "of an" between fraction and unit
            remainder = re.sub(r"^of\s+(?:a|an)\s+", "", remainder)
            if remainder:
                return val, remainder

    # Try "N and a half X"
    m = re.match(r"(\d+(?:\.\d+)?)\s+and\s+(\w+(?:\s+\w+)?)\s+(.+)", t)
    if m:
        whole = _parse_number(m.group(1))
        frac = _FRACTIONS.get(m.group(2).strip())
        if whole is not None and frac is not None:
            return whole + frac, m.group(3).strip()

    # Try word number: "a liter", "one cup", "an ounce"
    for word, val in _WORD_NUMS.items():
        if t.startswith(word + " "):
            remainder = t[len(word):].strip()
            if remainder:
                return float(val), remainder

    # Bare unit with implied 1: "cup", "liter"
    resolved = _resolve_unit(t)
    try:
        _ureg.parse_expression(f"1 {resolved}")
        return 1.0, t
    except Exception:
        pass

    return None, None


# --- Math expressions ---

_MATH_OPS = {
    "plus": "+", "and": "+",
    "minus": "-", "subtract": "-",
    "times": "*", "multiplied by": "*", "x": "*",
    "divided by": "/", "over": "/",
    "to the power of": "**", "raised to": "**",
}


def _try_math(text):
    """Try to parse and evaluate a math expression. Returns response string or None."""
    t = text.lower().strip().rstrip("?.")

    # "square root of N"
    m = re.search(r"(?:the\s+)?square\s+root\s+of\s+([\d,]+(?:\.\d+)?)", t)
    if m:
        n = _parse_number(m.group(1))
        if n is not None:
            result = math.sqrt(n)
            return f"The square root of {_fmt_number(n)} is {_fmt_number(result)}."

    # "N squared"
    m = re.search(r"([\d,]+(?:\.\d+)?)\s+squared", t)
    if m:
        n = _parse_number(m.group(1))
        if n is not None:
            result = n ** 2
            return f"{_fmt_number(n)} squared is {_fmt_number(result)}."

    # "N cubed"
    m = re.search(r"([\d,]+(?:\.\d+)?)\s+cubed", t)
    if m:
        n = _parse_number(m.group(1))
        if n is not None:
            result = n ** 3
            return f"{_fmt_number(n)} cubed is {_fmt_number(result)}."

    # "N% of M"
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*%\s*(?:of\s+)?([\d,]+(?:\.\d+)?)", t)
    if m:
        pct = _parse_number(m.group(1))
        base = _parse_number(m.group(2))
        if pct is not None and base is not None:
            result = (pct / 100) * base
            return f"{_fmt_number(pct)}% of {_fmt_number(base)} is {_fmt_number(result)}."

    # "N percent of M" (Whisper spells it out)
    m = re.search(r"([\d,]+(?:\.\d+)?)\s+percent\s+of\s+([\d,]+(?:\.\d+)?)", t)
    if m:
        pct = _parse_number(m.group(1))
        base = _parse_number(m.group(2))
        if pct is not None and base is not None:
            result = (pct / 100) * base
            return f"{_fmt_number(pct)} percent of {_fmt_number(base)} is {_fmt_number(result)}."

    # Binary operations: "N op M"
    # Try multi-word ops first, then single-word
    for op_word, op_sym in sorted(_MATH_OPS.items(), key=lambda x: -len(x[0])):
        m = re.search(
            rf"([\d,]+(?:\.\d+)?)\s+{re.escape(op_word)}\s+([\d,]+(?:\.\d+)?)", t)
        if m:
            a = _parse_number(m.group(1))
            b = _parse_number(m.group(2))
            if a is not None and b is not None:
                if op_sym == "/" and b == 0:
                    return "I can't divide by zero."
                result = eval(f"{a} {op_sym} {b}")
                return f"{_fmt_number(a)} {op_word} {_fmt_number(b)} is {_fmt_number(result)}."

    return None


# --- Command scoring and handling ---

def _classify(text):
    """Classify: returns 'unit', 'math', or None."""
    t = text.lower()
    if re.search(r"\bhow\s+many\s+\w+.*\bin\b", t):
        return "unit"
    if re.search(r"\bconvert\s+.+\s+to\b", t):
        return "unit"
    # "what is X in Y" where Y looks like a unit
    if re.search(r"\bwhat(?:'s|\s+is)\s+.+\s+in\s+(?:fahrenheit|celsius|feet|meters|"
                 r"inches|cups|tablespoons|teaspoons|ounces|pounds|grams|kilograms|"
                 r"liters|gallons|quarts|pints|miles|kilometers|centimeters|millimeters"
                 r"|milliliters|yards)\b", t):
        return "unit"
    if re.search(r"\b(plus|minus|times|divided by|multiplied by|percent|squared|cubed"
                 r"|square root|to the power)\b", t):
        return "math"
    if re.search(r"\d+\s*%\s*(?:of\s+)?\d+", t):
        return "math"
    return None


def score(text):
    cls = _classify(text)
    if cls is not None:
        return 0.9
    return 0.0


def handle(text):
    cls = _classify(text)

    if cls == "unit":
        result = _try_unit_conversion(text)
        if result:
            return result
        # Fall through to try math in case classification was wrong
        result = _try_math(text)
        if result:
            return result
        return "Sorry, I couldn't figure out that conversion."

    if cls == "math":
        result = _try_math(text)
        if result:
            return result
        # Fall through to try units
        result = _try_unit_conversion(text)
        if result:
            return result
        return "Sorry, I couldn't figure out that calculation."

    return "Sorry, I didn't understand that."


# --- Standalone test ---

if __name__ == "__main__":
    tests = [
        # Unit conversions
        "how many tablespoons in a quarter cup",
        "how many tablespoons in a cup",
        "how many cups in a liter",
        "how many feet in a mile",
        "how many ounces in a pound",
        "how many teaspoons in a tablespoon",
        "how many milliliters in a teaspoon",
        "convert 72 fahrenheit to celsius",
        "convert 100 celsius to fahrenheit",
        "what's 5 feet in centimeters",
        "how many cups in a half gallon",
        "how many tablespoons in three quarters cup",
        # Math
        "what's 347 times 23",
        "what is 15% of 85",
        "what's 15 percent of 200",
        "what is 144 divided by 12",
        "what's 5 plus 3",
        "what's 100 minus 37",
        "what's the square root of 144",
        "what is 7 squared",
        "what's 3 cubed",
        "what is 2 to the power of 8",
    ]
    for t in tests:
        cls = _classify(t)
        if cls == "unit":
            result = _try_unit_conversion(t)
        elif cls == "math":
            result = _try_math(t)
        else:
            result = None
        print(f"  [{cls or '?':4s}] {t!r:55s} => {result}")
