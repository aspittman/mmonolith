"""Transparent market evidence and bounded prediction feedback.

Inputs are authorized structured exports, not scraped or invented observations.
Predictions are supplied by the research provider only when it has evidence.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp, isfinite, sqrt
from statistics import mean, pstdev
import re
from uuid import UUID, uuid5, NAMESPACE_URL


def timestamp(value):
    value = re.sub(r'(T\d{2}:\d{2}:\d{2}\.)(\d{1,6})(?=[+-]|Z|$)',
                   lambda match: match[1] + match[2].ljust(6, '0'), value)
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def numeric(value, lower=0, upper=float('inf')):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not lower <= value <= upper:
        raise ValueError('Invalid numeric evidence')
    return float(value)


@dataclass(frozen=True)
class Policy:
    prior_samples: float = 100
    half_life_days: float = 90
    independent_sources_target: int = 3
    minimum_sample: int = 30
    max_confidence_change: float = .05
    internal_weight: float = .35
    tolerance: float = .10

    def __post_init__(self):
        if min(self.prior_samples, self.half_life_days, self.independent_sources_target, self.minimum_sample) <= 0:
            raise ValueError('Positive sample and recency policy required')
        for value in (self.max_confidence_change, self.internal_weight, self.tolerance):
            numeric(value, 0, 1)


class JSONEvidenceProvider:
    """Boundary for licensed API transformations, authorized CSV exports and research.

    The JSON carries source references, reliability, independent observation counts,
    normalized scores and explicit measured/estimated provenance. No source is fetched.
    """
    def __init__(self, path):
        self.path = path

    def load(self):
        import json
        from pathlib import Path
        return json.loads(Path(self.path).read_text())


def summarize(evidence, at, policy):
    if not evidence:
        return None, 0
    scores, weights, sources = [], [], set()
    for row in evidence:
        score = numeric(row['score'], 0, 100)
        n = numeric(row['sample_size'])
        reliability = numeric(row['reliability'], 0, 1)
        age = (at - timestamp(row['observed_at'])).total_seconds() / 86400
        if age < 0 or not row.get('source_reference') or row.get('evidence_type') not in ('measured', 'estimated', 'inferred'):
            raise ValueError('Evidence needs past observation, provenance and type')
        weight = reliability * exp(-age * .693147 / policy.half_life_days) * n / (n + policy.prior_samples)
        scores.append(score); weights.append(weight); sources.add(row['independent_source'])
    if not sum(weights):
        return None, 0
    opportunity = sum(s*w for s,w in zip(scores, weights)) / sum(weights)
    agreement = max(.2, 1 - pstdev(scores)/50)
    confidence = mean(weights) * min(1, sqrt(len(sources)/policy.independent_sources_target)) * agreement
    return round(opportunity, 4), round(confidence, 6)


def evaluate(prediction, result, policy):
    """Generic ratio or scalar metric; unknown/zero denominators are not zero rates."""
    spec = prediction.get('metadata', {})
    metrics = result['metrics']
    numerator, denominator = spec.get('numerator'), spec.get('denominator')
    actual, sample = None, 0
    if numerator and denominator:
        if metrics.get(numerator) is not None and metrics.get(denominator) is not None:
            count = numeric(metrics[numerator]); total = numeric(metrics[denominator])
            if count > total:
                raise ValueError('Ratio numerator exceeds denominator')
            sample = int(total)
            actual = count/total if total else None
    elif metrics.get(prediction['metric']) is not None:
        actual = numeric(metrics[prediction['metric']], -float('inf'))
        sample = int(numeric(metrics.get(spec.get('sample_metric', 'sample_size'), 0)))
    confidence = numeric(prediction['confidence'], 0, 1)
    low = prediction.get('expected_min', prediction.get('expected_value'))
    high = prediction.get('expected_max', prediction.get('expected_value'))
    if low is None: low = prediction.get('expected_value')
    if high is None: high = prediction.get('expected_value')
    label = 'INSUFFICIENT_DATA'
    after = confidence
    if actual is not None and sample >= policy.minimum_sample:
        if (low is None or actual >= low) and (high is None or actual <= high): label = 'SUPPORTED'
        elif high is not None and actual > high:
            label = 'PARTIALLY_SUPPORTED' if actual <= high + abs(high)*policy.tolerance else 'EXCEEDED_EXPECTATION'
        elif low is not None and actual >= low - abs(low)*policy.tolerance: label = 'PARTIALLY_SUPPORTED'
        else: label = 'NOT_SUPPORTED'
        change = policy.max_confidence_change * sample/(sample+policy.prior_samples)
        after = max(0, min(1, confidence + (change if label == 'SUPPORTED' else -change)))
    return {'prediction_id':prediction['id'],'execution_result_id':result['id'], 'actual_value':actual,
            'sample_size':sample,'evaluation':label,'confidence_after':round(after,6),
            'notes':'Per-execution observation; sample-weighted confidence. Original prediction remains immutable.'}


def build_bundle(org, run_key, research, context, policy=Policy(), at=None):
    UUID(org)
    at = at or datetime.now(timezone.utc)
    subject = research['subject_key']
    is_test = research.get('is_test') is True
    for rows in context.values():
        if any(row.get('organization_id') != org for row in rows):
            raise ValueError('Cross-organization evidence rejected')
    evidence = research['evidence']
    external = [r for r in evidence if r['scope']=='external']
    if len(external)!=len(evidence):
        raise ValueError('Internal evidence must come from attributable CRM outcomes')
    score, confidence = summarize(external,at,policy)
    if score is None:
        raise ValueError('Insufficient external evidence to create market report')
    reports = [r for r in context.get('intelligence_reports',[]) if r.get('subject_key')==subject and r.get('is_test',False)==is_test]
    previous = max(reports,key=lambda r:r['created_at']) if reports else None
    report_ids={r['id'] for r in reports}
    feedback = [f for f in context.get('feedback_evaluations',[]) if f['intelligence_report_id'] in report_ids and f['evaluation']!='INSUFFICIENT_DATA']
    # Repeated evaluations of the same result do not count as independent observations.
    by_result={f['execution_result_id']:f for f in sorted(feedback,key=lambda f:f['created_at'])}
    feedback=list(by_result.values())
    internal=None; internal_confidence=0
    if feedback:
        values=[]; weights=[]
        for f in feedback:
            target=f.get('predicted_value')
            if target is None and f.get('predicted_min') is not None and f.get('predicted_max') is not None:
                target=(f['predicted_min']+f['predicted_max'])/2
            if target is None or target<=0 or f['actual_value'] is None: continue
            age=max(0,(at-timestamp(f['created_at'])).total_seconds()/86400)
            w=f['sample_size']/(f['sample_size']+policy.prior_samples)*exp(-age*.693147/policy.half_life_days)
            values.append(min(100,50*f['actual_value']/target)); weights.append(w)
        if sum(weights):
            internal=sum(v*w for v,w in zip(values,weights))/sum(weights)
            internal_confidence=mean(weights)*min(1,sqrt(len(weights)/policy.independent_sources_target))
    external_confidence=confidence
    if feedback:
        # Anchor to current external evidence, never repeatedly accumulate old feedback.
        delta=mean(f.get('confidence_after', confidence)-f.get('confidence_before', confidence) for f in feedback)
        confidence=max(0,min(1,confidence+max(-policy.max_confidence_change,min(policy.max_confidence_change,delta))*internal_confidence))
    blend=policy.internal_weight*internal_confidence
    combined=score if internal is None else score*(1-blend)+internal*blend
    signals=[]
    for metric in sorted({r['metric'] for r in external}):
        value, certainty=summarize([r for r in external if r['metric']==metric],at,policy)
        if value is None: continue
        signals.append({'metric':metric,'value_numeric':value,'confidence_score':certainty,
          'source':'mmonolith.domain_intelligence','observed_at':at.isoformat(),
          'metadata':{'scope':'external','evidence':[r for r in external if r['metric']==metric]}})
    predictions=[]
    for p in research.get('predictions',[]):
        if not p.get('metadata',{}).get('evidence_reference'):
            raise ValueError('Prediction needs an evidence reference')
        predictions.append(dict(p))
    return {'report':{'run_key':run_key,'subject_key':subject,'subject_type':'domain_market','report_type':'DOMAIN_MARKET',
      'summary':research['hypothesis'] + (' Internal execution performance is tracked separately from external market attractiveness.' if feedback else ''),
      'overall_score':round(combined,4),'confidence_score':confidence,'previous_report_id':previous['id'] if previous else None,
      'correlation_id':previous['correlation_id'] if previous else str(uuid5(NAMESPACE_URL,org+':'+run_key)), 'is_test':is_test,
      'metadata':{'external_confidence':external_confidence,'external_market_score':score,'internal_performance_score':internal,'internal_confidence':internal_confidence,
        'hypothesis':research['hypothesis'],'policy':vars(policy),'subject_key':subject}},
      'signals':signals,'predictions':predictions,'feedback_ids':[f['id'] for f in feedback]}


def learn(client, org, policy=Policy()):
    context=client.context(org)
    existing={(f['prediction_id'],f['execution_result_id']) for f in context['feedback_evaluations']}
    reports={r['id']:r for r in context['intelligence_reports']}
    requests={r['id']:r for r in context['execution_requests']}
    links={(e['recommendation_id'],e.get('intelligence_report_id')) for e in context['recommendation_evidence']}
    ids=[]
    for p in context['predictions']:
        report=reports[p['intelligence_report_id']]
        for result in context['execution_results']:
            q=requests[result['execution_request_id']]
            if ((p['id'],result['id']) in existing or result['subject_key']!=p['subject_key'] or
                result.get('results',{}).get('is_test',False)!=report.get('is_test',False) or
                (q['recommendation_id'],report['id']) not in links or
                not timestamp(p['measurement_window_start'])<=timestamp(result['completed_at'])<=timestamp(p['measurement_window_end'])):
                continue
            ids.append(client.evaluate(org,evaluate(p,result,policy)))
    # Observational feedback needs no invented forecast or market-confidence boost.
    observed = {f['execution_result_id'] for f in context['feedback_evaluations'] if f.get('evaluation_kind') == 'OUTCOME_REVIEW'}
    for result in context['execution_results']:
        if result['id'] in observed or result.get('status') != 'COMPLETED': continue
        details = result.get('results', {})
        if details.get('review_contract') != 'domain-evidence-review-v1' or details.get('is_test') is not False: continue
        request = requests.get(result['execution_request_id'])
        report_id = details.get('intelligence_report_id')
        if not request or request.get('action_type') != 'review_domain_evidence' or report_id not in reports: continue
        if (request['recommendation_id'], report_id) not in links: continue
        ids.append(client.observe_review(org, result['id']))
    return ids
