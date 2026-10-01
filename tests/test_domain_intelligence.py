import copy
import unittest
from datetime import datetime, timedelta, timezone
from services.domain_intelligence.service import Policy, summarize, evaluate, build_bundle, timestamp

ORG='11111111-1111-4111-8111-111111111111'
NOW=datetime.now(timezone.utc)


def evidence(n=1000,score=80,days=0,source='one'):
    return {'scope':'external','metric':'buyer_density','score':score,'sample_size':n,'reliability':.9,
            'observed_at':(NOW-timedelta(days=days)).isoformat(),'source_reference':'fixture://test',
            'independent_source':source,'evidence_type':'measured'}


class DomainIntelligenceTest(unittest.TestCase):
    def test_postgrest_fractional_timestamp(self):
        self.assertEqual(timestamp('2026-09-15T15:32:56.55585-06:00').microsecond,555850)

    def test_small_samples_recency_and_independence(self):
        policy=Policy()
        large=summarize([evidence()],NOW,policy)[1]
        self.assertGreater(large,summarize([evidence(n=3)],NOW,policy)[1])
        self.assertGreater(large,summarize([evidence(days=180)],NOW,policy)[1])
        self.assertGreater(summarize([evidence(source=str(i)) for i in range(3)],NOW,policy)[1],large)
        self.assertLess(summarize([evidence(score=10),evidence(score=100)],NOW,policy)[1],large)

    def test_ratio_evaluation_immutable_and_bounded(self):
        p={'id':'prediction','metric':'reply_rate','expected_min':.03,'expected_max':.06,'confidence':.8,
           'metadata':{'numerator':'replies','denominator':'emails_delivered'}}
        original=copy.deepcopy(p)
        result={'id':'result','metrics':{'replies':31,'emails_delivered':480}}
        evaluation=evaluate(p,result,Policy())
        self.assertEqual(evaluation['evaluation'],'PARTIALLY_SUPPORTED')
        self.assertAlmostEqual(evaluation['actual_value'],31/480)
        self.assertLessEqual(abs(evaluation['confidence_after']-.8),.05)
        self.assertEqual(original,p)
        result['metrics']={'replies':1,'emails_delivered':3}
        self.assertEqual(evaluate(p,result,Policy())['evaluation'],'INSUFFICIENT_DATA')
        result['metrics']={'replies':0,'emails_delivered':0}
        self.assertIsNone(evaluate(p,result,Policy())['actual_value'])
        result['metrics']={'replies':2,'emails_delivered':1}
        with self.assertRaises(ValueError): evaluate(p,result,Policy())

    def test_private_context_and_imported_internal_rejected(self):
        research={'subject_key':'hvac','hypothesis':'test','evidence':[evidence()]}
        with self.assertRaises(ValueError): build_bundle(ORG,'one',research,{'intelligence_reports':[{'organization_id':'other'}]},at=NOW)
        research['evidence'][0]['scope']='internal'
        with self.assertRaises(ValueError): build_bundle(ORG,'one',research,{},at=NOW)

    def test_external_internal_separate_and_new_version(self):
        research={'subject_key':'hvac','hypothesis':'test','is_test':True,'evidence':[evidence()]}
        first=build_bundle(ORG,'one',research,{},at=NOW)
        old={**first['report'],'id':'old','organization_id':ORG,'created_at':NOW.isoformat()}
        context={'intelligence_reports':[old],'feedback_evaluations':[{'id':'feedback','organization_id':ORG,
          'intelligence_report_id':'old','execution_result_id':'outcome','evaluation':'NOT_SUPPORTED','predicted_min':.03,
          'predicted_max':.06,'predicted_value':None,'actual_value':.001,'sample_size':480,'created_at':NOW.isoformat()}]}
        snapshot=copy.deepcopy(context)
        second=build_bundle(ORG,'two',research,context,at=NOW)
        self.assertEqual(second['report']['previous_report_id'],'old')
        self.assertEqual(second['report']['metadata']['external_market_score'],80)
        self.assertLess(second['report']['overall_score'],first['report']['overall_score'])
        self.assertEqual(second['feedback_ids'],['feedback'])
        self.assertEqual(snapshot,context)
        research['is_test']=False
        live=build_bundle(ORG,'live',research,context,at=NOW)
        self.assertEqual(live['feedback_ids'],[])
        self.assertIsNone(live['report']['previous_report_id'])

    def test_malformed_or_missing_evidence_fails_closed(self):
        for value in [float('nan'),True,-1,101]:
            with self.assertRaises(ValueError): summarize([evidence(score=value)],NOW,Policy())
        with self.assertRaises(ValueError): summarize([evidence(days=-1)],NOW,Policy())

if __name__=='__main__': unittest.main()
