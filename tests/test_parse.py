"""Data-driven test suite for command parsing.

Reads test cases from test_cases.txt and validates that each input is
correctly classified to the expected module/command with expected arguments,
without executing any side effects.

See test_cases.txt for the format specification.
"""

import pytest
from pathlib import Path

from hecko.commands import ALL_COMMANDS as _ALL_MODULES


def best_parse(text):
    """Parse text against all modules, return the winning Parse or None."""
    parses = []
    for mod in _ALL_MODULES:
        p = mod.parse(text)
        if p is not None:
            p.module = mod
            parses.append(p)
    if not parses:
        return None
    parses.sort(key=lambda p: -p.score)
    return parses[0]


def _module_name(p):
    """Get the short module name from a Parse."""
    if p is None or p.module is None:
        return "none"
    return p.module.__name__.split(".")[-1]


def _parse_value(s):
    """Parse a string value into the appropriate Python type."""
    if s == "true":
        return True
    if s == "false":
        return False
    if s == "none":
        return None
    if s == "nonempty":
        return s  # sentinel
    try:
        if "." in s:
            return float(s)
        if s.lstrip("-").isdigit():
            return int(s)
    except ValueError:
        pass
    return s


def _load_test_cases():
    """Load test cases from test_cases.txt."""
    path = Path(__file__).parent / "test_cases.txt"
    cases = []
    current = None

    for line_num, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("> "):
            if current:
                cases.append(current)
            current = {
                "input": stripped[2:],
                "module": "none",
                "checks": [],
                "expected_args": {},      # plain arg keys expected
                "expected_dotted": {},    # dotted arg keys expected (arg_name -> set of attrs)
                "line": line_num,
            }
            continue

        if current is None:
            continue

        # key: value
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if key == "module":
            current["module"] = value
        elif key == "command":
            current["checks"].append(("command", value))
        elif key == "score":
            current["checks"].append(("score", float(value)))
        elif "." in key:
            arg_name, attr = key.split(".", 1)
            parsed_val = _parse_value(value)
            current["checks"].append(("dotted", arg_name, attr, parsed_val))
            current["expected_dotted"].setdefault(arg_name, set()).add(attr)
        else:
            parsed_val = _parse_value(value)
            current["checks"].append(("arg", key, parsed_val))
            current["expected_args"][key] = parsed_val

    if current:
        cases.append(current)

    return cases


_CASES = _load_test_cases()


def _fmt_parse(p):
    """Format a Parse for failure output."""
    if p is None:
        return "None (no match)"
    parts = [f"module={_module_name(p)}, command={p.command}, score={p.score}"]
    for k, v in p.args.items():
        if k == "teams":
            parts.append(f"teams=[{len(v)} team(s)]")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


@pytest.mark.parametrize("case", _CASES, ids=[c["input"] for c in _CASES])
def test_parse(case):
    text = case["input"]
    expected_module = case["module"]
    p = best_parse(text)
    actual_module = _module_name(p)

    # No-match case
    if expected_module == "none":
        assert p is None, (
            f"\n  Input:    {text!r}"
            f"\n  Expected: no match"
            f"\n  Got:      {_fmt_parse(p)}"
        )
        return

    # Should have matched
    assert p is not None, (
        f"\n  Input:    {text!r}"
        f"\n  Expected: module={expected_module}"
        f"\n  Got:      no match"
    )

    # Check module
    assert actual_module == expected_module, (
        f"\n  Input:    {text!r}"
        f"\n  Expected: module={expected_module}"
        f"\n  Got:      {_fmt_parse(p)}"
    )

    # Check each assertion
    for check in case["checks"]:
        kind = check[0]

        if kind == "command":
            expected_cmd = check[1]
            assert p.command == expected_cmd, (
                f"\n  Input:    {text!r}"
                f"\n  Expected: command={expected_cmd}"
                f"\n  Got:      {_fmt_parse(p)}"
            )

        elif kind == "score":
            expected_score = check[1]
            assert p.score == expected_score, (
                f"\n  Input:    {text!r}"
                f"\n  Expected: score={expected_score}"
                f"\n  Got:      {_fmt_parse(p)}"
            )

        elif kind == "arg":
            key, expected_val = check[1], check[2]
            if expected_val == "nonempty":
                actual = p.args.get(key, [])
                assert len(actual) > 0, (
                    f"\n  Input:    {text!r}"
                    f"\n  Expected: args[{key!r}] nonempty"
                    f"\n  Got:      {_fmt_parse(p)}"
                )
            else:
                actual_val = p.args.get(key)
                assert actual_val == expected_val, (
                    f"\n  Input:    {text!r}"
                    f"\n  Expected: args[{key!r}]={expected_val!r}"
                    f"\n  Got:      args[{key!r}]={actual_val!r}"
                    f"\n  Full:     {_fmt_parse(p)}"
                )

        elif kind == "dotted":
            arg_name, attr, expected_val = check[1], check[2], check[3]
            obj = p.args.get(arg_name)
            actual_val = getattr(obj, attr, None)
            assert actual_val == expected_val, (
                f"\n  Input:    {text!r}"
                f"\n  Expected: args[{arg_name!r}].{attr}={expected_val!r}"
                f"\n  Got:      args[{arg_name!r}].{attr}={actual_val!r}"
                f"\n  Full:     {_fmt_parse(p)}"
            )

    # Check for unexpected args not mentioned in the test case.
    # Args checked via plain "key: value" or dotted "key.attr: value"
    # must account for every key in p.args.
    mentioned_args = set(case["expected_args"].keys()) | set(case["expected_dotted"].keys())
    actual_args = set(p.args.keys())
    extra = actual_args - mentioned_args
    if extra:
        extra_detail = ", ".join(f"{k}={p.args[k]!r}" for k in sorted(extra))
        assert False, (
            f"\n  Input:    {text!r}"
            f"\n  Unexpected args not in test case: {extra_detail}"
            f"\n  Full:     {_fmt_parse(p)}"
            f"\n  Add these to test_cases.txt or remove from the parse."
        )
