"""Entry point for `python -m hecko`."""

import sys


def _parse_cmd(text):
    """Parse a single input and print the result in test_cases.txt format."""
    from hecko.commands import ALL_COMMANDS as modules

    parses = []
    for mod in modules:
        p = mod.parse(text)
        if p is not None:
            p.module = mod
            parses.append(p)

    print(f"> {text}")

    if not parses:
        print("module: none")
        return

    parses.sort(key=lambda p: -p.score)
    best = parses[0]
    mod_name = best.module.__name__.split(".")[-1]

    print(f"module: {mod_name}")
    print(f"command: {best.command}")

    for key, val in best.args.items():
        if hasattr(val, "hour"):
            # datetime-like: print dotted attributes
            print(f"{key}.hour: {val.hour}")
            print(f"{key}.minute: {val.minute}")
        elif isinstance(val, list):
            if val:
                print(f"{key}: nonempty")
            else:
                print(f"{key}: empty")
        elif isinstance(val, bool):
            print(f"{key}: {'true' if val else 'false'}")
        elif val is None:
            print(f"{key}: none")
        elif isinstance(val, float):
            print(f"{key}: {val}")
        elif isinstance(val, int):
            print(f"{key}: {val}")
        else:
            print(f"{key}: {val}")


if __name__ == "__main__" or not sys.argv[0]:
    if len(sys.argv) >= 3 and sys.argv[1] == "-parse":
        _parse_cmd(" ".join(sys.argv[2:]))
    else:
        from hecko.main import main
        main()
