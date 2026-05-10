"""Dev — Experimentation Frontend Developer Agent"""

import anthropic
from pathlib import Path

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "frontend_dev.md"
THEME_ROOT = Path.home() / "Desktop" / "claude_folder" / "codebase_ryzon"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def load_theme_context(page_type: str) -> str:
    """Load relevant Shopify theme files for a page type."""
    PAGE_FILES = {
        "PDP": [
            "sections/main-product.liquid",
            "snippets/buy-buttons.liquid",
            "snippets/product-media-gallery.liquid",
        ],
        "PLP": [
            "sections/main-collection-product-grid.liquid",
            "sections/main-collection-banner.liquid",
            "snippets/card-product.liquid",
        ],
        "Homepage": [
            "sections/image-banner.liquid",
            "sections/featured-collection.liquid",
            "snippets/card-product.liquid",
        ],
        "Cart": [
            "sections/cart-drawer.liquid",
            "sections/main-cart-items.liquid",
            "sections/main-cart-footer.liquid",
        ],
    }

    files = PAGE_FILES.get(page_type, [])
    context_parts = []
    for rel_path in files:
        path = THEME_ROOT / rel_path
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="ignore")[:12000]
            context_parts.append(f"--- {rel_path} ---\n{content}")

    return "\n\n".join(context_parts) if context_parts else ""


def create_agent(client: anthropic.Anthropic, model: str = "claude-sonnet-4-6"):
    return {
        "name": "Dev",
        "role": "Frontend Developer",
        "system_prompt": load_prompt(),
        "client": client,
        "model": model,
    }


def run(agent: dict, user_message: str, context: str = "", page_type: str = "") -> str:
    """Run Dev on a task. Optionally loads theme files for the given page_type."""
    full_context = context
    if page_type:
        theme = load_theme_context(page_type)
        if theme:
            full_context = f"THEME FILES:\n{theme}\n\n{context}" if context else f"THEME FILES:\n{theme}"

    messages = []
    if full_context:
        messages.append({
            "role": "user",
            "content": f"<context>\n{full_context}\n</context>\n\n{user_message}",
        })
    else:
        messages.append({"role": "user", "content": user_message})

    response = agent["client"].messages.create(
        model=agent["model"],
        max_tokens=4096,
        system=agent["system_prompt"],
        messages=messages,
    )
    return response.content[0].text
