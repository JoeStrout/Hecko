"""Stock price command: look up current prices and compare to past prices."""

import re
from hecko.commands.template import TemplatePattern
from hecko.commands.parse import Parse

# Map common names (lowercase) to Yahoo Finance ticker symbols
_SYMBOLS = {
    # Companies
    "apple": "AAPL",
    "microsoft": "MSFT",
    "tesla": "TSLA",
    "hewlett packard enterprise": "HPE",
    "hpe": "HPE",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "nvidia": "NVDA",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "disney": "DIS",
    "boeing": "BA",
    "intel": "INTC",
    "amd": "AMD",
    # Indices
    "s&p 500": "^GSPC",
    "s&p": "^GSPC",
    "s and p": "^GSPC",
    "s and p 500": "^GSPC",
    "dow": "^DJI",
    "dow jones": "^DJI",
    "nasdaq": "^IXIC",
    # Commodities
    "gold": "GC=F",
    "silver": "SI=F",
}

# Display names for non-company symbols
_DISPLAY_NAMES = {
    "^GSPC": "The S&P 500",
    "^DJI": "The Dow",
    "^IXIC": "The Nasdaq",
    "GC=F": "Gold",
    "SI=F": "Silver",
}

_PRICE_PATTERNS = [
    TemplatePattern("[how is|how's] $stock doing", greedy=True),
    TemplatePattern("[how is|how's] $stock doing today", greedy=True),
    TemplatePattern("[what is|what's] the stock price [of|for] $stock", greedy=True),
    TemplatePattern("[what is|what's] the current price [of|for] $stock", greedy=True),
    TemplatePattern("[what is|what's] the price of $stock", greedy=True),
    TemplatePattern("[what is|what's] $stock [worth|trading at|at]", greedy=True),
    TemplatePattern("[what is|what's] $stock [worth|trading at|at] today", greedy=True),
    TemplatePattern("$stock stock price", greedy=True),
    TemplatePattern("$stock price", greedy=True),
    TemplatePattern("stock price of $stock", greedy=True),
    TemplatePattern("[check|get] [the |]price of $stock", greedy=True),
    TemplatePattern("[check|get] [the |]stock price of $stock", greedy=True),
]

_COMPARE_PATTERNS = [
    TemplatePattern("compare $stock to $interval ago"),
    TemplatePattern("[how is|how's] $stock [doing |][compared to|versus|vs] $interval ago"),
]

_WHAT_WAS_PATTERNS = [
    TemplatePattern("[what was|what's|where was] $stock $interval ago"),
    TemplatePattern("[what was|what's|where was] the $stock $interval ago"),
    TemplatePattern("[what was|what's|where was] the price of $stock $interval ago"),
]

# Word-to-number mapping for interval parsing
_WORD_NUMS = {
    "a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}

# Map interval units to yfinance period suffixes and day counts
_UNIT_MAP = {
    "day": ("d", 1), "days": ("d", 1),
    "week": ("d", 7), "weeks": ("d", 7),
    "month": ("mo", 30), "months": ("mo", 30),
    "year": ("y", 365), "years": ("y", 365),
}


def _parse_interval(text):
    """Parse an interval like 'a month', 'three weeks', '6 months'.

    Returns (yf_period, label) or (None, None).
    Label is e.g. 'a month', 'three weeks'.
    """
    t = text.strip().lower()
    m = re.match(r'^(\w+)\s+(day|days|week|weeks|month|months|year|years)$', t)
    if not m:
        return None, None

    num_word = m.group(1)
    unit = m.group(2)

    if num_word in _WORD_NUMS:
        n = _WORD_NUMS[num_word]
    elif num_word.isdigit():
        n = int(num_word)
    else:
        return None, None

    suffix, days_per = _UNIT_MAP[unit]

    if suffix == "d":
        period = f"{n * days_per}d"
    elif suffix == "mo":
        period = f"{n}mo"
    elif suffix == "y":
        period = f"{n}y"
    else:
        return None, None

    # Build a readable label
    if n == 1:
        singular = unit.rstrip("s")
        label = f"a {singular}"
    else:
        plural = unit if unit.endswith("s") else unit + "s"
        label = f"{num_word} {plural}"

    return period, label


def _resolve_symbol(name):
    """Resolve a stock name or ticker to a Yahoo Finance symbol.

    Returns (symbol, display_name) or (None, None).
    """
    stripped = re.sub(r'\s+stock$', '', name.strip().rstrip("."), flags=re.IGNORECASE)
    clean = stripped.lower()
    # Try exact name match
    if clean in _SYMBOLS:
        symbol = _SYMBOLS[clean]
        display = _DISPLAY_NAMES.get(symbol, stripped)
        return symbol, display
    # Try as raw ticker (uppercase)
    upper = clean.upper()
    if re.match(r'^[A-Z]{1,5}$', upper):
        return upper, upper
    return None, None


def _clean_stock(stock):
    """Clean up a captured stock name."""
    stock = re.sub(r'^(the|a)\s+', '', stock, flags=re.IGNORECASE)
    return stock


def _try_interval_patterns(patterns, text, command):
    """Try matching text against patterns with an $interval field."""
    for pat in patterns:
        m = pat.match(text)
        if m is not None:
            stock = _clean_stock(m.get("stock", ""))
            interval = m.get("interval", "").strip()
            if stock and interval:
                period, label = _parse_interval(interval)
                if period:
                    return Parse(command=command, score=0.95,
                                 args={"stock": stock, "period": period,
                                       "label": label})
    return None


def parse(text):
    # Try compare patterns first (more specific)
    p = _try_interval_patterns(_COMPARE_PATTERNS, text, "compare")
    if p:
        return p
    p = _try_interval_patterns(_WHAT_WAS_PATTERNS, text, "what_was")
    if p:
        return p

    # Standard price patterns
    for pat in _PRICE_PATTERNS:
        m = pat.match(text)
        if m is not None:
            stock = _clean_stock(m.get("stock", ""))
            if stock:
                return Parse(command="stock_price", score=0.9,
                             args={"stock": stock})
    return None


def _fetch_price(symbol, period="7d"):
    """Fetch current price and oldest price in the given period.

    Returns (current_price, past_price) or raises on error.
    """
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period)
    if hist.empty:
        raise ValueError(f"No data for {symbol}")
    current = hist["Close"].iloc[-1]
    past = hist["Close"].iloc[0] if len(hist) > 1 else None
    return current, past


def _format_price(price, is_index=False):
    """Format a price for display."""
    if is_index or price >= 1000:
        return f"{price:,.2f}"
    return f"{price:.2f}"


def _format_pct(pct):
    """Format a percentage, dropping '.0' when it's a whole number."""
    s = f"{abs(pct):.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return f"{s}%"


def _format_response(display, symbol, current, past, interval_label):
    """Format a stock price response with optional comparison."""
    is_index = symbol.startswith("^")
    price_str = _format_price(current, is_index)

    if is_index:
        result = f"{display} is at {price_str}"
    else:
        result = f"{display} is at ${price_str}"

    if past is not None:
        diff = current - past
        pct = (diff / past) * 100
        direction = "up" if diff >= 0 else "down"
        diff_str = _format_price(abs(diff), is_index)
        if is_index:
            result += f", {direction} {diff_str} points ({_format_pct(pct)}) from {interval_label} ago."
        else:
            result += f", {direction} ${diff_str} ({_format_pct(pct)}) from {interval_label} ago."
    else:
        result += "."

    return result


def _format_what_was(display, symbol, current, past, interval_label):
    """Format a past-focused response: report old price, then diff to today."""
    is_index = symbol.startswith("^")
    dollar = "" if is_index else "$"

    if past is None:
        return f"Sorry, I don't have data for {display} from {interval_label} ago."

    past_str = _format_price(past, is_index)
    current_str = _format_price(current, is_index)
    diff = current - past
    pct = (diff / past) * 100
    direction = "up" if diff >= 0 else "down"
    diff_str = _format_price(abs(diff), is_index)

    if is_index:
        return (f"{display} was at {past_str} {interval_label} ago. "
                f"It's now at {current_str}, {direction} {diff_str} points ({_format_pct(pct)}).")
    return (f"{display} was at {dollar}{past_str} {interval_label} ago. "
            f"It's now at {dollar}{current_str}, {direction} {dollar}{diff_str} ({_format_pct(pct)}).")


def handle(p):
    stock_name = p.args["stock"]
    symbol, display = _resolve_symbol(stock_name)
    if symbol is None:
        return f"Sorry, I don't know the ticker symbol for {stock_name}."

    period = p.args.get("period", "7d")
    label = p.args.get("label", "a week")

    try:
        current, past = _fetch_price(symbol, period)
    except Exception as e:
        return f"Sorry, I couldn't get the price for {display}. {e}"

    if p.command == "what_was":
        return _format_what_was(display, symbol, current, past, label)
    return _format_response(display, symbol, current, past, label)
