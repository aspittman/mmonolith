"""Extract named implementation technologies separately from customer needs."""
from __future__ import annotations

import re

TECHNOLOGIES: dict[str, tuple[str, ...]] = {
    "Stripe": (r"\bstripe\b",), "PayPal": (r"\bpaypal\b",),
    "OpenAI": (r"\bopenai\b", r"\bgpt-?[345]\b"), "ChatGPT": (r"\bchatgpt\b",),
    "Twilio": (r"\btwilio\b",), "HubSpot": (r"\bhubspot\b",),
    "Salesforce": (r"\bsalesforce\b",), "Supabase": (r"\bsupabase\b",),
    "Firebase": (r"\bfirebase\b",), "Shopify": (r"\bshopify\b",),
    "WooCommerce": (r"\bwoocommerce\b",), "WordPress": (r"\bwordpress\b",),
    "React": (r"\breact(?:\.js|js)?\b",), "Next.js": (r"\bnext(?:\.js|js)\b",),
    "Python": (r"\bpython\b",), "Zapier": (r"\bzapier\b",),
    "Make": (r"\bmake\.com\b", r"\bintegromat\b"), "n8n": (r"\bn8n\b",),
    "Webflow": (r"\bwebflow\b",), "Squarespace": (r"\bsquarespace\b",),
}


def extract_technologies(title: str, description: str) -> list[str]:
    text = f"{title}\n{description}".lower()
    return [name for name, patterns in TECHNOLOGIES.items() if any(re.search(p, text) for p in patterns)]

