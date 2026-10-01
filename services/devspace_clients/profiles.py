"""Explicit profiles live in organization_services.config_json.client_research."""
from dataclasses import dataclass
from uuid import UUID
from .modules import MODULES


def strings(value, name, required=False):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f'{name} must be a list of nonempty strings')
    if required and not value:
        raise ValueError(f'{name} is required')
    return tuple(dict.fromkeys(x.strip() for x in value))


@dataclass(frozen=True)
class ClientProfile:
    organization_id: str
    profile_id: str
    business_type: str
    offer: str
    objective: str
    locations: tuple
    target_terms: tuple
    queries: tuple
    modules: tuple
    excluded_domains: tuple
    max_prospects: int
    max_queries: int
    min_fit_score: int

    @classmethod
    def from_service(cls, row):
        org = str(UUID(row['organization_id']))
        if row.get('service_key') != 'devspace_clients' or row.get('is_enabled') is not True:
            raise ValueError('An enabled devspace_clients service is required')
        config = row.get('config_json', {}).get('client_research', {})
        if config.get('enabled') is not True:
            raise ValueError('Client research is not configured/enabled')
        text = {}
        config = {**config, 'objective': config.get('objective', 'customers')}
        for key in ('business_type', 'offer', 'objective'):
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise ValueError(f'{key} is required')
            text[key] = config[key].strip()
        if text['objective'] not in ('customers', 'partners', 'competitors'):
            raise ValueError('Unsupported research objective')
        limits = {}
        for key, default, maximum in (('max_prospects', 25, 100), ('max_queries', 5, 20), ('min_fit_score', 60, 100)):
            value = config.get(key, default)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f'Invalid {key}')
            limits[key] = value
        modules = strings(config.get('modules', ['prospect_discovery']), 'modules', True)
        if set(modules) - set(MODULES) or 'prospect_discovery' not in modules:
            raise ValueError('Unknown research module')
        return cls(org, str(UUID(row['id'])), **text,
            locations=strings(config.get('locations', []), 'locations', True),
            target_terms=strings(config.get('target_terms', []), 'target_terms', True),
            queries=strings(config.get('queries', []), 'queries', True), modules=modules,
            excluded_domains=strings(config.get('excluded_domains', []), 'excluded_domains'), **limits)
