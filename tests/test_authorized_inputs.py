import json
from datetime import datetime,timezone
import pytest
from services.domain_intelligence.authorized_inputs import quotes


def test_checkout_export_preserves_provider_and_total(tmp_path):
 at=datetime.now(timezone.utc);path=tmp_path/'quotes.json'
 row={'domain':'example.test','provider':'GoDaddy','price_type':'checkout_total','currency':'USD','checked_at':at.isoformat(),'acquisition_price':12,'status':'available'}
 data={'organization_id':'org','subject_key':'loans','source_url':'https://example.test/receipt','retrieved_at':at.isoformat(),'contract':'registrar-checkout-quotes-v1','quotes':[row]}
 path.write_text(json.dumps(data))
 assert quotes(path,'org','loans',['example.test'],at)['example.test']['provider']=='GoDaddy'
 with pytest.raises(ValueError):quotes(path,'another-org','loans',['example.test'],at)
 row['price_type']='advertised_price';path.write_text(json.dumps(data))
 with pytest.raises(ValueError):quotes(path,'org','loans',['example.test'],at)
