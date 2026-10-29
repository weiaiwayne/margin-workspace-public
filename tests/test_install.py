"""Installer configuration and no-side-effect plan validation; no host mutation."""
import importlib.util,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('margin_install',ROOT/'deploy/install.py')
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)

def test_production_configuration():
    config,broker=install.configuration('margin.example.com',['/srv/margin-projects','/srv/projects'])
    assert config['secure_cookie'] and config['proxy'] and config['base_path']=='/'
    assert config['hosts']==['margin.example.com','localhost','127.0.0.1']
    assert config['projects']['shared']['root']=='/srv/margin/projects/shared'
    assert broker['socket']==config['workspace_broker_socket']
    assert broker['document_sources']['shared']=='/srv/margin-projects/shared'
    assert 'default_agent_access' not in broker

def test_proxy_never_serves_http_login():
    plain=install.nginx('margin.example.com')
    assert 'return 503' in plain and 'proxy_pass' not in plain
    secure=install.nginx('margin.example.com',True)
    assert 'return 301 https://' in secure and 'proxy_pass http://127.0.0.1:8766' in secure
    assert 'proxy_request_buffering off' in secure and 'ssl_protocols TLSv1.2 TLSv1.3' in secure

def test_plan_is_safe_in_unprivileged_empty_directory(tmp_path):
    p=subprocess.run([sys.executable,str(ROOT/'deploy/install.py'),'--domain','margin.example.com','--email','admin@example.com','--plan'],cwd=tmp_path,text=True,capture_output=True)
    assert p.returncode==0,p.stderr
    assert json.loads(p.stdout)['admin']=='admin'
    assert list(tmp_path.iterdir())==[]

def test_reject_injected_hostname_before_work(tmp_path):
    p=subprocess.run([sys.executable,str(ROOT/'deploy/install.py'),'--domain','example.com;bad','--email','admin@example.com','--plan'],cwd=tmp_path,text=True,capture_output=True)
    assert p.returncode!=0 and list(tmp_path.iterdir())==[]
