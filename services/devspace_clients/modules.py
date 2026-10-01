"""Research modules produce observations; fit is an explicit heuristic, not demand."""
import hashlib
import ipaddress
import socket
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests

DIRECTORIES = {'facebook.com', 'instagram.com', 'linkedin.com', 'yelp.com', 'yellowpages.com',
    'google.com', 'bing.com', 'youtube.com', 'reddit.com', 'wikipedia.org', 'x.com'}


def term_matches(term, text):
    def words(value):
        return {word.removesuffix('s') if len(word) > 3 else word for word in re.findall(r'[a-z0-9]+', value.casefold())
            if word not in {'the', 'of', 'and', 'for'}}
    tokens = words(term)
    return bool(tokens) and tokens <= words(text)


def public_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Public HTTP(S) URL required')
    host = parsed.hostname.lower().removeprefix('www.')
    if host == 'localhost' or '.' not in host or parsed.port not in (None, 80, 443):
        raise ValueError('Public website required')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('Private website rejected')
    except ValueError as error:
        if str(error) == 'Private website rejected':
            raise
    return value, host


def qualify(profile, rows, provider):
    candidates, seen = [], set()
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        try:
            website, domain = public_url(row.get('website', ''))
        except (ValueError, TypeError):
            continue
        if domain in seen or any(domain == d or domain.endswith('.' + d) for d in (*profile.excluded_domains, *DIRECTORIES)):
            continue
        seen.add(domain)
        text = (row.get('company_name', '') + ' ' + row.get('description', '')).casefold()
        matched = [term for term in profile.target_terms if term_matches(term, text)]
        location = row.get('location')
        verified_location = location in profile.locations and row.get('location_evidence') == 'source'
        score = min(100, (60 if matched else 0) + (40 if verified_location else 0))
        missing = []
        if provider != 'authorized_export': missing.append('Business identity and buying need require confirmation')
        if not matched: missing.append('Target customer fit is unverified')
        if not verified_location: missing.append('Service-area fit needs verification')
        if not row.get('contact', {}).get('email'): missing.append('Recipient needs verification')
        candidates.append({'id': hashlib.sha256((profile.organization_id + ':' + profile.profile_id + ':' + domain).encode()).hexdigest()[:24],
            'organization_id': profile.organization_id, 'company_name': row.get('company_name') or domain,
            'website': website, 'domain': domain, 'location': location,
            'contact': row.get('contact', {}), 'objective': profile.objective,
            'fit_score': score, 'fit_confidence': .7 if matched and verified_location else .35 if matched else 0,
            'status': 'REVIEW' if score >= profile.min_fit_score else 'NEEDS_RESEARCH',
            'fit_reasons': ['Target terms observed: ' + ', '.join(matched)] if matched else [],
            'missing_information': missing, 'findings': [],
            'evidence': [{'source': row.get('source', provider), 'source_reference': row.get('source_reference') or website,
                'observed_at': now, 'evidence_type': 'reported', 'excerpt': row.get('description', ''),
                'query': row.get('query'), 'location_evidence': row.get('location_evidence')}],
            'offer': profile.offer})
    return sorted(candidates, key=lambda r: (-r['fit_score'], r['domain']))[:profile.max_prospects]


def audit_websites(candidates):
    for candidate in candidates:
        try:
            parsed = urlparse(candidate['website'])
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise ValueError('Nonpublic address')
            # Redirects are observations, never followed to a different/private target.
            with requests.get(candidate['website'], timeout=10, allow_redirects=False, stream=True) as response:
                candidate['findings'].append({'metric': 'website_http_status', 'value': response.status_code,
                    'source_reference': candidate['website'], 'observed_at': datetime.now(timezone.utc).isoformat()})
        except (requests.RequestException, OSError, ValueError):
            candidate['missing_information'].append('Website availability could not be verified')


MODULES = {'prospect_discovery': qualify, 'website_audit': audit_websites}
