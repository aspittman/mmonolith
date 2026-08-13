"""Extract the business problem, independently of service and technology labels."""
from __future__ import annotations

import re

PAIN_POINTS: dict[str, tuple[str, ...]] = {
    "slow website": (r"slow (?:website|site)", r"website speed", r"core web vitals"),
    "broken website": (r"broken (?:website|site)", r"website (?:error|bug|issue)", r"site (?:error|bug)"),
    "needs redesign": (r"(?:needs?|need a) redesign", r"website redesign", r"outdated (?:website|site)"),
    "needs payment system": (r"payment (?:system|gateway|integration)", r"stripe integration", r"checkout"),
    "needs CRM connection": (r"crm (?:connection|integration|sync)", r"connect .{0,20} (?:hubspot|salesforce)"),
    "needs lead automation": (r"lead automation", r"automate .{0,25}(?:leads|follow.?up|sales)"),
    "needs chatbot": (r"(?:ai )?chatbot", r"chat assistant"),
    "emails not sending": (r"emails? (?:not|isn't|aren't) (?:sending|delivered)", r"smtp (?:problem|issue|fix)"),
    "forms broken": (r"forms? (?:broken|not working|not sending)", r"contact form (?:issue|fix|problem)"),
    "security issue": (r"security (?:issue|problem|fix|audit)", r"vulnerabilit", r"hacked (?:site|website)"),
    "malware": (r"malware", r"malicious code"),
    "poor conversions": (r"poor conversions?", r"conversion (?:problem|issue|optimi[sz]ation)", r"not converting"),
    "needs booking system": (r"booking (?:system|integration)", r"appointment schedul"),
    "needs database integration": (r"database integration", r"connect .{0,20} database", r"data migration"),
}


def extract_pain_points(title: str, description: str) -> list[str]:
    text = f"{title}\n{description}".lower()
    return [name for name, patterns in PAIN_POINTS.items() if any(re.search(p, text) for p in patterns)]

