"""shortener utils"""

from shortener.services.keygen import default_kgs


def generate_uuid() -> str:
    """Generate the next unique short key via the Key Generation Service."""
    return default_kgs.next_key()
