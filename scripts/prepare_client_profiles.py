"""Prepare client profiles from the confirmed business inventory; no database writes."""
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

CLIENTS = [
    ('62539265-e1ae-4e14-8360-416747590585', 'Fletcher Tropical Snow', 'frozen treats', 'Snow cones for events',
        ['event organizers', 'festival organizers', 'school events'], ['event venues', 'party planners'], ['snow cone vendors']),
    ('0da3f571-a388-490f-90b9-e08e3609159f', 'Randys Brazilian Lemonade', 'beverage vendor', 'Brazilian lemonade for events',
        ['event organizers', 'festival organizers', 'corporate events'], ['event venues', 'food truck parks'], ['lemonade vendors']),
    ('88c1cb4f-e471-4d4b-8708-a87b3f4a229c', 'Microgreen Network', 'microgreens', 'Microgreens for food businesses',
        ['restaurants', 'chefs', 'grocery stores'], ['farmers markets', 'food distributors'], ['microgreens farms']),
    ('76b76aa2-8989-4fe9-a234-c16ddcbce989', 'Colombian Flavor', 'food vendor', 'Colombian food for events',
        ['event organizers', 'festival organizers', 'corporate events'], ['event venues', 'party planners'], ['Colombian food vendors']),
    ('20ea8b66-cc49-48e5-972e-2e89ed9a27e5', 'Gather Around', 'networking events', 'Networking events for Utah businesses',
        ['business owners', 'entrepreneurs', 'startup founders'], ['chambers of commerce', 'coworking spaces'], ['business networking events']),
    ('fe127a4a-3e4a-4bbe-b85a-9d09ce396e2d', 'Phoenician Tech', 'business software', 'Software for technology companies',
        ['technology companies', 'tech startups'], ['technology consultants', 'software consultants'], ['business software vendors']),
]
rows = []
for org, name, business_type, offer, customers, referrals, competition in CLIENTS:
    config = {'enabled': True, 'business_type': business_type, 'offer': offer, 'objective': 'customers',
        'ideal_customers': ', '.join(customers), 'target_terms': customers,
        'referral_partners': ', '.join(referrals), 'referral_terms': referrals,
        'competitors': ', '.join(competition), 'competitor_terms': competition, 'locations': ['Utah'],
        'excluded_domains': [], 'queries': [term+' {location}' for term in customers], 'modules': ['prospect_discovery'],
        'referrals': {'queries': [term+' {location}' for term in referrals], 'target_terms': referrals},
        'competition': {'queries': [term+' {location}' for term in competition], 'target_terms': competition},
        'max_queries': 3, 'max_prospects': 25, 'min_fit_score': 60}
    rows.append({'id': str(uuid5(NAMESPACE_URL, org+':devspace_clients:client-growth')),
        'organization_id': org, 'service_key': 'devspace_clients', 'service_name': 'DevSpace Clients',
        'niche': 'client-growth', 'is_enabled': True, 'email_enabled': False, 'approval_required': True,
        'config_json': {'client_research': config, 'profile_source': 'initial_setup',
            'needs_client_confirmation': True, 'business_name': name}})
root = Path('data/devspace_clients'); root.mkdir(parents=True, exist_ok=True)
path = root/'initial_profiles.json'; path.write_text(json.dumps(rows, indent=2)+'\n')
print(json.dumps({'profiles_path': str(path), 'prepared_clients': len(rows),
    'needs_business_description': ['Synapse'], 'excluded_service_organizations': ['Domain Merchant', 'Apollo Outreach', 'DevSpace Technologies']}))
