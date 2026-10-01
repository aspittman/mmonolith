"""Independent cron-compatible CLI with a durable local publication outbox."""
import argparse
import json
import os
import sqlite3
from pathlib import Path
from .client import LoopClient
from .service import JSONEvidenceProvider, Policy, build_bundle, learn


def main():
    parser=argparse.ArgumentParser(description='Publish domain market intelligence and evaluate CRM outcomes')
    parser.add_argument('--organization',required=True)
    parser.add_argument('--run-key')
    parser.add_argument('--evidence')
    parser.add_argument('--learn',action='store_true')
    parser.add_argument('--policy',help='JSON Policy configuration')
    parser.add_argument('--outbox',default='data/domain_intelligence.sqlite3')
    args=parser.parse_args()
    policy=Policy(**json.loads(Path(args.policy).read_text())) if args.policy else Policy()
    client=LoopClient(os.environ['CRM_BASE_URL'],os.environ['BOT_API_SECRET'])
    if args.learn:
        print(json.dumps({'organization_id':args.organization,'feedback_ids':learn(client,args.organization,policy)}))
    if args.evidence:
        if not args.run_key: parser.error('--run-key required with --evidence')
        Path(args.outbox).parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(args.outbox) as db:
            db.execute('create table if not exists publications(organization_id text,run_key text,bundle text,report_id text,primary key(organization_id,run_key))')
            saved=db.execute('select bundle from publications where organization_id=? and run_key=?',(args.organization,args.run_key)).fetchone()
            if saved: bundle=json.loads(saved[0])
            else:
                research=JSONEvidenceProvider(args.evidence).load()
                if research.get('is_test') and os.getenv('DEVSPACE_ENV')!='test':
                    raise ValueError('Test evidence requires DEVSPACE_ENV=test')
                bundle=build_bundle(args.organization,args.run_key,research,client.context(args.organization),policy)
                db.execute('insert into publications values(?,?,?,null)',(args.organization,args.run_key,json.dumps(bundle,allow_nan=False)))
                db.commit()  # Preserve exact request across offline/ambiguous response failures.
            report_id=client.publish(args.organization,bundle)
            db.execute('update publications set report_id=? where organization_id=? and run_key=?',(report_id,args.organization,args.run_key))
            print(json.dumps({'organization_id':args.organization,'intelligence_report_id':report_id,'correlation_id':bundle['report']['correlation_id']}))
    elif not args.learn: parser.error('Choose --learn and/or --evidence')


if __name__=='__main__': main()
