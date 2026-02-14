"""Ask Claude — forward a question to the Anthropic API and return the response."""

from hecko.commands.template import TemplatePattern
from hecko.commands.parse import Parse

_PATTERNS = [
    TemplatePattern("ask [Claude|cloud] $message", greedy=True),
    TemplatePattern("[hey|hi] [Claude|cloud] $message", greedy=True),
    TemplatePattern("[Claude|cloud] $message", greedy=True),
]

_client = None


def _get_client():
    global _client
    if _client is None:
        from hecko.claude_credentials import ANTHROPIC_API_KEY
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def parse(text):
    # Strip commas/periods that Whisper may insert after "Claude"
    clean = text.replace(",", "").replace(".", "").replace(":", "")
    for pat in _PATTERNS:
        m = pat.match(clean)
        if m is not None:
            message = m.get("message", "").strip()
            if message:
                return Parse(command="ask", score=0.9, args={"message": message})
    return None


def handle(p):
    message = p.args["message"]
    try:
        client = _get_client()
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=200,
            system="Reply briefly in one or two sentences.",
            messages=[{"role": "user", "content": message}],
        )
        answer = resp.content[0].text
        return f"Claude says, {answer}"
    except Exception as e:
        return f"Sorry, I couldn't reach Claude. {e}"
