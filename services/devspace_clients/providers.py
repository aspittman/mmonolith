"""Bounded public search or tenant-scoped authorized exports."""
import json
import os
from pathlib import Path
import requests


class ExportProvider:
    name = 'authorized_export'
    def __init__(self, path):
        self.payload = json.loads(Path(path).read_text())

    def discover(self, profile):
        if self.payload.get('organization_id') != profile.organization_id:
            raise ValueError('Export organization mismatch')
        rows = self.payload.get('prospects')
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Invalid prospect export')
        if any(r.get('organization_id', profile.organization_id) != profile.organization_id for r in rows):
            raise ValueError('Mixed-organization export')
        return [r for r in rows if r.get('objective', 'customers') == profile.objective][:profile.max_prospects]


class SerpAPIProvider:
    name = 'serpapi'
    def __init__(self):
        self.key = os.getenv('SERPAPI_API_KEY') or os.getenv('SERP_API_KEY')
        if not self.key:
            raise ValueError('SERPAPI_API_KEY is required')

    def discover(self, profile):
        rows, used = [], 0
        for location in profile.locations:
            for template in profile.queries:
                if used >= profile.max_queries or len(rows) >= profile.max_prospects:
                    return rows[:profile.max_prospects]
                query = template.format(location=location, business_type=profile.business_type)
                try:
                    response = requests.get('https://serpapi.com/search.json', params={
                        'engine': 'google', 'api_key': self.key, 'q': query, 'num': 10},
                        timeout=30, allow_redirects=False)
                except requests.RequestException:
                    raise RuntimeError('Search provider connection failed') from None
                used += 1
                if response.status_code != 200:
                    raise RuntimeError('Search provider failed')
                try:
                    body = response.json()
                except ValueError:
                    raise RuntimeError('Invalid search provider response') from None
                if body.get('error'):
                    raise RuntimeError('Search provider rejected request')
                for item in body.get('organic_results', []):
                    rows.append({'company_name': item.get('title', ''), 'website': item.get('link', ''),
                        'description': item.get('snippet', ''), 'location': location,
                        'location_evidence': 'search_query', 'query': query, 'source': self.name})
        return rows[:profile.max_prospects]
