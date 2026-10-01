"""Explicitly synthetic evidence for isolated integration tests. Never live research."""
from datetime import datetime, timedelta, timezone
from devspace_domain_research.market_data import normalize_sale
from services.domain_intelligence.research import build_research


def fixture_bundle(org,run_key,context):
    at=datetime.now(timezone.utc)-timedelta(seconds=1)
    sales=[]
    for suffix in ('pros','experts','service','repair','quotes','systems','solutions','contractors','install','maintenance','commercial','residential'):
        sale,_=normalize_sale({'domain':'hvac'+suffix+'.com','sale_price':1000,'sale_date':at.date().isoformat(),
          'currency':'USD','source_name':'synthetic_test_sales','source_quality':'tier_2','transaction_type':'reported_sale',
          'source_url':'https://example.test/synthetic-sales'})
        sales.append(sale)
    domain='hvacserviceexample.com'
    demand={'source':'synthetic_test_keywords','source_url':'https://example.test/keywords','retrieved_at':at.isoformat(),
      'evidence_type':'provider_estimate','keywords':[{'keyword':'hvac','search_volume':1200,'cpc':4,'competition_index':70}]}
    buyers={'organization_id':org,'subject_key':'hvac','source_url':'https://example.test/buyers','retrieved_at':at.isoformat(),
      'companies':[{'domain':'buyer.example','name':'Synthetic HVAC Company','fit_reason':'Synthetic HVAC contractor fixture'}]}
    quote={domain:{'status':'available','provider':'GoDaddy','simulation':True,'price_type':'checkout_total','source_url':'https://example.test/synthetic-registrar','checked_at':at.isoformat(),
      'acquisition_price':12,'renewal_price':20,'currency':'USD'}}
    bundle=build_research(org,run_key,'hvac',['hvac'],[],sales,demand=demand,buyers=buyers,availability=quote,
      candidates=[domain],context=context,is_test=True,legacy=True,limit=1,at=at)
    bundle['predictions']=[{'metric':'reply_rate','expected_min':.03,'expected_max':.06,'confidence':.8,
      'measurement_window_start':at.isoformat(),'measurement_window_end':(at+timedelta(days=30)).isoformat(),
      'metadata':{'numerator':'replies','denominator':'emails_delivered','evidence_reference':'fixture://synthetic/reply-baseline'}}]
    return bundle
