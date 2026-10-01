"""Four-repository domain loop: real Next.js + PostgREST + PostgreSQL; synthetic auth provider.

Usage: python scripts/smoke_domain_loop.py --engine-root ../decision_engine --postgrest /path/to/postgrest
No deployed database is used. Domain Merchant runs in enforced test mode with no external actions.
"""
import argparse
import base64
import hashlib
import hmac
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import psycopg
from psycopg.types.json import Jsonb
import pgserver

MM_ROOT=Path(__file__).resolve().parents[1]
ROOT=MM_ROOT.parent/'devspace-crm'
sys.path.insert(0,str(MM_ROOT))
ORG='11111111-1111-4111-8111-111111111111'
ADMIN='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
JWT_SECRET='local-decision-smoke-secret-never-deploy-this'

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]

def b64(data): return base64.urlsafe_b64encode(data).decode().rstrip('=')

def token(role,sub=None):
    data={'role':role,'exp':int(time.time())+3600, 'aud':'authenticated'}
    if sub: data['sub']=sub
    body=b64(b'{"alg":"HS256","typ":"JWT"}')+'.'+b64(json.dumps(data).encode())
    return body+'.'+b64(hmac.new(JWT_SECRET.encode(),body.encode(),hashlib.sha256).digest())

class Forms(HTMLParser):
    def __init__(self): super().__init__(); self.forms=[]; self.current=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='form': self.current={}; self.forms.append(self.current)
        if tag=='input' and self.current is not None and attrs.get('name'):
            self.current[attrs['name']]=attrs.get('value','')
    def handle_endtag(self,tag):
        if tag=='form': self.current=None

def main():
    args=argparse.ArgumentParser()
    args.add_argument('--engine-root',required=True);args.add_argument('--postgrest',required=True)
    args=args.parse_args()
    sys.path.insert(0,str(Path(args.engine_root).resolve()))
    from decision_engine.clients.crm_client import CRMClient
    from decision_engine.repositories.crm import CRMRepository
    from decision_engine.config.settings import scoring_config
    from decision_engine.services.decision_service import DecisionService
    with tempfile.TemporaryDirectory(prefix='crm-de-smoke-') as temp:
        temp=Path(temp);server=pgserver.get_server(temp/'pg')
        processes=[]; proxy=None
        try:
            with psycopg.connect(server.get_uri(),autocommit=True) as db:
                db.execute('''create role anon; create role authenticated; create role service_role bypassrls;
                  create schema auth; create table auth.users(id uuid primary key);
                  create function auth.uid() returns uuid language sql as $$ select coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),current_setting('request.jwt.claims',true)::jsonb->>'sub')::uuid $$;
                  grant usage on schema auth to authenticated,service_role;
                ''')
                for path in sorted((ROOT/'supabase/migrations').glob('*.sql')):
                    db.execute(path.read_text().replace('create extension if not exists pgcrypto;',''))
                db.execute('grant select on organizations,profiles,organization_services to authenticated; grant all on all tables in schema public to service_role')
                db.execute("insert into organizations(id,name) values(%s,'Decision Engine Development')",(ORG,))
                db.execute('insert into auth.users values(%s)',(ADMIN,))
                db.execute("insert into profiles(id,email,role,organization_id) values(%s,'aaron@devspacetechnologies.com','admin',%s)",(ADMIN,ORG))
                db.execute("insert into organization_services(organization_id,service_key,service_name) values(%s,'domain_merchant','Development domain research')",(ORG,))
                db.execute('insert into decision_constraints(organization_id,constraints) values(%s,%s)',(ORG,Jsonb({'monthly_marketing_budget':1500,'email_reputation_healthy':True,'risk_tolerance':'MEDIUM'})))
                rest_port,proxy_port,crm_port=port(),port(),port()
                rest_url=f'http://127.0.0.1:{rest_port}'
                crm_url=f'http://127.0.0.1:{crm_port}'
                user_token=token('authenticated',ADMIN)
                user={'id':ADMIN,'aud':'authenticated','role':'authenticated','email':'aaron@devspacetechnologies.com','app_metadata':{},'user_metadata':{},'created_at':'2026-01-01T00:00:00Z'}
                class Proxy(BaseHTTPRequestHandler):
                    def log_message(self,*_): pass
                    def do_GET(self): self.forward()
                    def do_POST(self): self.forward()
                    def forward(self):
                        if self.path.startswith('/auth/v1/user'):
                            allowed=self.headers.get('Authorization')=='Bearer '+user_token
                            self.send_response(200 if allowed else 401);self.send_header('Content-Type','application/json');self.end_headers()
                            self.wfile.write(json.dumps(user if allowed else {'error':'Unauthorized'}).encode());return
                        if not self.path.startswith('/rest/v1/'):
                            self.send_error(404);return
                        body=self.rfile.read(int(self.headers.get('Content-Length','0'))) if self.command=='POST' else None
                        headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','content-length','connection')}
                        try: response=urlopen(Request(rest_url+self.path[len('/rest/v1'):],data=body,headers=headers,method=self.command),timeout=20)
                        except HTTPError as error: response=error
                        with response:
                            self.send_response(response.status)
                            for k,v in response.headers.items():
                                if k.lower() in ('content-type','content-range'):self.send_header(k,v)
                            self.end_headers();self.wfile.write(response.read())
                proxy=ThreadingHTTPServer(('127.0.0.1',proxy_port),Proxy)
                threading.Thread(target=proxy.serve_forever,daemon=True).start()
                env={**os.environ,'PGRST_DB_URI':server.get_uri(),'PGRST_DB_SCHEMAS':'public','PGRST_DB_ANON_ROLE':'anon',
                    'PGRST_JWT_SECRET':JWT_SECRET,'PGRST_SERVER_HOST':'127.0.0.1','PGRST_SERVER_PORT':str(rest_port)}
                log=open(temp/'servers.log','w+')
                processes.append(subprocess.Popen([str(Path(args.postgrest).resolve())],env=env,stdout=log,stderr=log))
                env={**os.environ,'NEXT_PUBLIC_SUPABASE_URL':f'http://127.0.0.1:{proxy_port}', 'NEXT_PUBLIC_SUPABASE_ANON_KEY':token('anon'),
                    'SUPABASE_SERVICE_ROLE_KEY':token('service_role'),'BOT_API_SECRET':'local-smoke-bot-secret','NEXT_TELEMETRY_DISABLED':'1'}
                processes.append(subprocess.Popen(['node','node_modules/next/dist/bin/next','dev','--hostname','127.0.0.1','--port',str(crm_port)],cwd=ROOT,env=env,stdout=log,stderr=log))
                client=CRMClient(crm_url,'local-smoke-bot-secret',timeout=60)
                for attempt in range(60):
                    try: client.get_organizations();break
                    except Exception:
                        if attempt==59:raise RuntimeError('Local CRM startup failed')
                        time.sleep(1)
                os.environ['DEVSPACE_ENV']='test'
                from services.domain_intelligence.client import LoopClient
                from services.domain_intelligence.service import build_bundle, learn
                from datetime import datetime, timedelta, timezone
                loop=LoopClient(crm_url,'local-smoke-bot-secret')
                at=datetime.now(timezone.utc)-timedelta(seconds=1)
                from domain_research_fixture import fixture_bundle
                bundle=fixture_bundle(ORG,'safe-cycle-1',loop.context(ORG))
                report=loop.publish(ORG,bundle)
                assert loop.publish(ORG,bundle)==report
                assert db.execute('select count(*) from leads where intelligence_report_id=%s',(report,)).fetchone()[0]==1
                original=db.execute('select row_to_json(r) from intelligence_reports r where id=%s',(report,)).fetchone()[0]
                prediction=db.execute('select row_to_json(p) from predictions p where intelligence_report_id=%s',(report,)).fetchone()[0]
                config=scoring_config()
                result=DecisionService(CRMRepository(client,config),config).run(ORG)
                rec=next(r for r in result['recommendations'] if r['recommendation_type']=='DOMAIN_ACQUISITION')
                session={'access_token':user_token,'refresh_token':'local-only','expires_at':int(time.time())+3600,'expires_in':3600,'token_type':'bearer','user':user}
                cookie='sb-127-auth-token=base64-'+b64(json.dumps(session).encode())
                page_url=crm_url+'/admin/recommendations?organization_id='+ORG
                with urlopen(Request(page_url,headers={'Cookie':cookie}),timeout=90) as response: html=response.read().decode()
                assert rec['title'] in html and 'Decision Engine Development' in html and 'View Evidence' in html, 'Recommendation absent from CRM UI'
                with urlopen(Request(crm_url+'/admin/domain-portfolio?tab=recommendations',headers={'Cookie':cookie}),timeout=90) as response: portfolio=response.read().decode()
                assert 'Researched by MMonolith' in portfolio and 'hvacserviceexample.com' in portfolio, 'Research missing from existing portfolio UI'
                parser=Forms();parser.feed(html)
                form=next(f for f in parser.forms if f.get('recommendation_id')==rec['id'])
                assert any(k.startswith('$ACTION') for k in form), 'Missing server action binding'
                form['decision']='APPROVED';form['reason']='Isolated development smoke test'
                # Multipart encoding preserves the server action metadata emitted by React.
                boundary='----DecisionSmokeBoundary'
                body=''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k,v in form.items())+f'--{boundary}--\r\n'
                with urlopen(Request(page_url,data=body.encode(),headers={'Cookie':cookie,'Origin':crm_url,'Content-Type':'multipart/form-data; boundary='+boundary},method='POST'),timeout=90) as response:
                    response.read()
                request=db.execute('select id,status from execution_requests where recommendation_id=%s and organization_id=%s',(rec['id'],ORG)).fetchone()
                assert request and request[1]=='APPROVED', 'Approval did not create a nonqueued request'
                assert db.execute('select count(*) from execution_results').fetchone()[0]==0
                # Prove a durable approved request survives adapter unavailability.
                db.execute("update execution_capabilities set adapter_ready=true where service_key='domain_merchant'")
                fixture=temp/'domain-fixture.json'
                fixture.write_text(json.dumps({'domains':['hvacserviceexample.com','hvacrepairdemo.com'],
                    'simulated_metrics':{'emails_delivered':480,'replies':31,'offers':3,'domains_sold':0}}))
                worker_env={**os.environ,'DEVSPACE_ENV':'test','CRM_BASE_URL':crm_url,'CRM_BOT_API_SECRET':'local-smoke-bot-secret'}
                subprocess.run([sys.executable,'-m','core.feedback_worker','--organization',ORG,'--fixture',str(fixture),
                    '--outbox',str(temp/'outbox')],cwd=MM_ROOT.parent/'devspace-one',env=worker_env,check=True)
                outcome=db.execute('select row_to_json(x) from execution_results x where execution_request_id=%s',(request[0],)).fetchone()[0]
                assert outcome['results']['is_test'] and outcome['metrics']['replies']==31
                feedback=learn(loop,ORG)
                assert len(feedback)==1 and learn(loop,ORG)==[]
                updated_bundle=fixture_bundle(ORG,'safe-cycle-2',loop.context(ORG))
                updated=loop.publish(ORG,updated_bundle)
                assert updated!=report and updated_bundle['report']['previous_report_id']==report
                assert updated_bundle['feedback_ids']==feedback
                assert db.execute('select row_to_json(r) from intelligence_reports r where id=%s',(report,)).fetchone()[0]==original
                assert db.execute('select row_to_json(p) from predictions p where id=%s',(prediction['id'],)).fetchone()[0]==prediction
                # Database protections apply even to a trusted backend writer.
                for statement, parameters in [
                    ("update predictions set expected_min=0 where id=%s",(prediction['id'],)),
                    ("delete from predictions where id=%s",(prediction['id'],)),
                    ("update intelligence_reports set summary='mutated' where id=%s",(report,)),
                    ("update feedback_evaluations set actual_value=0 where id=%s",(feedback[0],))]:
                    try: db.execute(statement,parameters)
                    except psycopg.Error: pass
                    else: raise AssertionError('Immutable history accepted mutation')
                other='22222222-2222-4222-8222-222222222222'
                db.execute("insert into organizations(id,name) values(%s,'Other isolated tenant')",(other,))
                assert all(not rows for rows in loop.context(other).values())
                try: loop.evaluate(other,{'prediction_id':prediction['id'],'execution_result_id':outcome['id'],
                    'actual_value':0,'sample_size':480,'evaluation':'NOT_SUPPORTED','confidence_after':.5,'notes':'forbidden'})
                except RuntimeError: pass
                else: raise AssertionError('Cross-tenant evaluation accepted')
                # Same terminal result can be replayed after an ambiguous network failure.
                replay=loop.request('POST','results',ORG,execution_request_id=outcome['execution_request_id'],status='COMPLETED',
                    cost=0,revenue=None,metrics=outcome['metrics'],results=outcome['results'])
                assert replay==outcome['id']
                assert db.execute('select count(*) from execution_results where execution_request_id=%s',(request[0],)).fetchone()[0]==1
                db.execute('set role service_role')
                try:
                    try: db.execute("select de_review_and_request(%s,%s,'APPROVED')",(ORG,rec['id']))
                    except psycopg.Error: pass
                    else: raise AssertionError('Bot service could approve itself')
                finally: db.execute('reset role')
                second=DecisionService(CRMRepository(client,config),config).run(ORG)
                next_rec=next(r for r in second['recommendations'] if r['recommendation_type']=='DOMAIN_ACQUISITION')
                assert any(e['intelligence_report_id']==updated for e in next_rec['evidence'])
                trace={'organization_id':ORG,'correlation_id':bundle['report']['correlation_id'],
                    'intelligence_report_id':report,'recommendation_id':rec['id'],'execution_request_id':str(request[0]),
                    'execution_result_id':outcome['id'],'feedback_evaluation_id':feedback[0],'updated_intelligence_report_id':updated,
                    'next_recommendation_id':next_rec['id'],'crm_ui_verified':True,'approval_via_crm_form':True,'external_actions':0}
                print(json.dumps(trace,indent=2))
                (MM_ROOT/'data/processed/domain_loop_trace.json').parent.mkdir(parents=True,exist_ok=True)
                (MM_ROOT/'data/processed/domain_loop_trace.json').write_text(json.dumps(trace,indent=2))
        except Exception:
            if (temp/'servers.log').exists():
                print((temp/'servers.log').read_text()[-6000:],file=sys.stderr)
            raise
        finally:
            for process in reversed(processes):
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            if proxy:proxy.shutdown()
            server.cleanup()

if __name__=='__main__':main()
