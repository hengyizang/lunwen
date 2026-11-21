"""Match complete signed numeric tokens, never a favorable substring."""
from decimal import Decimal, InvalidOperation
import re

TOKEN = re.compile(r"(?<![\w.+−-])[+−-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+−-]?\d+)?(?!\w|\.\d)")


def number_in_text(text: str, rendered: str) -> bool:
    try:
        expected = Decimal(rendered.replace("−", "-"))
        if not expected.is_finite():
            return False
        return any(Decimal(token.group().replace("−", "-")) == expected for token in TOKEN.finditer(text))
    except (InvalidOperation, ValueError, AttributeError):
        return False
