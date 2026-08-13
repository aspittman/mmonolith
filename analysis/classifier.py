"""Deterministic service taxonomy classifier with phrase context and priorities."""
from __future__ import annotations

import re

SERVICE_CATEGORIES = (
    "API_INTEGRATION", "CRM_INTEGRATION", "PAYMENT_INTEGRATION", "AI_INTEGRATION",
    "AUTOMATION", "WEBSITE_DESIGN", "WEBSITE_REDESIGN", "WEBSITE_REPAIR",
    "PERFORMANCE_OPTIMIZATION", "WORDPRESS", "ECOMMERCE", "SEO_TECHNICAL",
    "ACCESSIBILITY", "SECURITY", "BOOKING_SYSTEM", "FORM_EMAIL_FIXES", "DATABASE",
    "CUSTOM_WEB_APP", "OTHER",
)

# Specific business outcomes appear before broad implementation types. Multiple matching
# phrases add evidence; title matches are weighted more heavily than body matches.
RULES: dict[str, tuple[str, ...]] = {
    "PAYMENT_INTEGRATION": (r"\bstripe\b", r"\bpaypal\b", r"payment (?:gateway|system|integration)", r"checkout (?:flow|integration)"),
    "CRM_INTEGRATION": (r"crm (?:integration|connection|sync)", r"\bhubspot\b", r"\bsalesforce\b", r"\bzoho crm\b"),
    "AI_INTEGRATION": (r"ai (?:chatbot|assistant|integration)", r"openai (?:api|integration)", r"chatgpt (?:api|integration|chatbot)", r"rag (?:system|chatbot)"),
    "BOOKING_SYSTEM": (r"booking (?:system|integration|calendar)", r"appointment schedul", r"\bcalendly\b"),
    "FORM_EMAIL_FIXES": (r"form(?:s)? (?:is |are )?(?:broken|not working|not sending)", r"emails? (?:not|isn't|aren't) (?:sending|delivered)", r"smtp (?:fix|issue)", r"contact form"),
    "PERFORMANCE_OPTIMIZATION": (r"(?:slow|speed up|optimi[sz]e) (?:my |our |the )?(?:website|site)", r"website speed", r"core web vitals", r"pagespeed"),
    "SECURITY": (r"malware", r"website secur", r"hacked (?:site|website)", r"security (?:audit|issue|fix)", r"vulnerabilit"),
    "ACCESSIBILITY": (r"web accessibility", r"\bwcag\b", r"\bada compliance\b", r"accessibility (?:audit|fix|remediation)"),
    "SEO_TECHNICAL": (r"technical seo", r"seo (?:audit|fix|issue)", r"schema markup", r"crawl (?:error|issue)", r"indexing (?:error|issue)"),
    "AUTOMATION": (r"workflow automation", r"business process automation", r"automate (?:our|my|the)", r"\bzapier\b", r"\bmake\.com\b", r"\bn8n\b"),
    "API_INTEGRATION": (r"api integration", r"integrat(?:e|ion|ing).{0,30}\bapi\b", r"connect .{0,25} (?:platform|system|app)", r"webhook"),
    "WEBSITE_REDESIGN": (r"website redesign", r"redesign (?:my|our|the) (?:site|website)", r"moderni[sz]e (?:my|our|the) (?:site|website)"),
    "WEBSITE_REPAIR": (r"(?:broken|fix|repair) (?:my |our |the )?(?:website|site)", r"website (?:bug|error|issue)", r"site (?:bug|error|issue)"),
    "ECOMMERCE": (r"e-?commerce (?:site|store|website|development)", r"\bshopify\b", r"\bwoocommerce\b", r"online store"),
    "WORDPRESS": (r"\bwordpress\b", r"\belementor\b", r"wordpress plugin"),
    "DATABASE": (r"database (?:integration|design|migration|issue)", r"\bsupabase\b", r"\bfirebase\b", r"data migration"),
    "WEBSITE_DESIGN": (r"(?:new |build |design )(?:a |my |our )?(?:website|site)", r"website design"),
    "CUSTOM_WEB_APP": (r"custom web app", r"web application", r"customer dashboard", r"client portal", r"saas (?:app|platform|development)"),
}


def classify_service(title: str, description: str) -> str:
    title_text, body_text = title.lower(), description.lower()
    scores: dict[str, int] = {}
    for category, patterns in RULES.items():
        title_hits = sum(bool(re.search(pattern, title_text)) for pattern in patterns)
        body_hits = sum(bool(re.search(pattern, body_text)) for pattern in patterns)
        if title_hits or body_hits:
            scores[category] = title_hits * 3 + body_hits
    return max(scores, key=scores.get) if scores else "OTHER"
