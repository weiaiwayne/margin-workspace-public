import hashlib
import sqlite3
import time
from pathlib import Path
import pytest
from app import create_app, digest
from werkzeug.security import generate_password_hash


@pytest.fixture
def workspace(tmp_path):
    root=tmp_path/'project'; root.mkdir()
    (root/'plans').mkdir()
    (root/'plans'/'test.md').write_text('# Test plan\n\nA passage to discuss.\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n![external](https://tracker.invalid/image.png)\n')
    (root/'.secret.md').write_text('secret')
    (root/'external').mkdir(); (root/'external'/'secret.md').write_text('secret')
    other=tmp_path/'other'; other.mkdir(); (other/'other.md').write_text('# Private')
    outside=tmp_path/'outside.md'; outside.write_text('secret'); (root/'linked.md').symlink_to(outside)
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(tmp_path/'db.sqlite'),'projects':{'one':{'root':str(root),'name':'One'},'two':{'root':str(other),'name':'Two'}}}
    app=create_app(config)
    with sqlite3.connect(config['database']) as db:
        for username,admin in [('admin',1),('reader',0),('outsider',0)]:
            db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,?)',(username,username,generate_password_hash('test-password-123'),admin))
        db.execute('INSERT INTO access VALUES(2,?)',('one',))
    return app,config,root


def signin(app,user='admin'):
    client=app.test_client()
    response=client.post('/api/login',json={'username':user,'password':'test-password-123'})
    assert response.status_code==200
    return client,{'X-CSRF-Token':response.json['csrf']}


def add(client,headers,**extra):
    revision=client.get('/api/document?project=one&path=plans/test.md').json['revision']
    return client.post('/api/comments',headers=headers,json={'project':'one','path':'plans/test.md','body':'Please clarify this.','revision':revision,'quote':'A passage to discuss.',**extra})


def test_auth_required_and_cookie(workspace):
    app,_,_=workspace
    c=app.test_client()
    assert c.get('/api/files?project=one').status_code==401
    assert c.get('/api/session').json['user'] is None
    assert c.post('/api/login',json={'username':'admin','password':'wrong'}).status_code==401
    c,h=signin(app)
    assert c.get('/api/session').json['user']['admin']
    assert c.post('/api/logout',headers=h,json={}).status_code==200
    assert c.get('/api/projects').status_code==401


def test_csrf_origin_and_host(workspace):
    c,h=signin(workspace[0])
    assert c.post('/api/export',json={}).status_code==403
    assert c.post('/api/export',headers={**h,'Origin':'https://evil.invalid'},json={}).status_code==403
    assert c.get('/api/session',headers={'Host':'evil.invalid'}).status_code==400


def test_project_permissions(workspace):
    c,h=signin(workspace[0],'reader')
    assert [p['id'] for p in c.get('/api/projects').json['projects']]==['one']
    assert c.get('/api/files?project=two').status_code==403
    assert c.get('/api/document?project=two&path=other.md').status_code==403
    assert c.get('/api/users').status_code==403
    assert c.post('/api/users',headers=h,json={}).status_code==403


@pytest.mark.parametrize('path',['../outside.md','/etc/passwd','.secret.md','external/secret.md','linked.md','plans/../../outside.md','.reviews/plans/test.md.review.md'])
def test_path_guards(workspace,path):
    c,h=signin(workspace[0])
    assert c.get('/api/document',query_string={'project':'one','path':path}).status_code in (400,403,404)


def test_listing_and_sanitizer(workspace):
    c,h=signin(workspace[0])
    assert [f['path'] for f in c.get('/api/files?project=one').json['files']]==['plans/test.md']
    r=c.get('/api/document?project=one&path=plans/test.md')
    assert '<h1' in r.json['html']
    assert '<script' not in r.json['html']
    assert 'javascript:' not in r.json['html']
    assert '<img' not in r.json['html']
    assert "script-src 'self'" in r.headers['Content-Security-Policy']


def test_threads_export_revision_and_source_preservation(workspace):
    app,config,root=workspace
    before=(root/'plans/test.md').read_bytes()
    c,h=signin(app,'reader')
    r=add(c,h); assert r.status_code==201
    cid=r.json['id']
    assert add(c,h,parent_id=cid,body='A reply').status_code==201
    assert c.post(f'/api/comments/{cid}/resolve',headers=h,json={'resolved':True}).status_code==200
    assert add(c,h,parent_id=cid).status_code==409
    r=c.post('/api/export',headers=h,json={'project':'one','path':'plans/test.md'})
    assert r.status_code==200
    exported=root/'.reviews/plans/test.md.review.md'
    assert exported.exists()
    assert 'A reply' in exported.read_text() and 'Resolved' in exported.read_text()
    assert (root/'plans/test.md').read_bytes()==before
    assert not c.get('/api/comments?project=one&path=plans/test.md').json['export']['dirty']
    (root/'plans/test.md').write_text('# Changed')
    assert c.get('/api/comments?project=one&path=plans/test.md').json['export']['dirty']
    assert c.post('/api/comments',headers=h,json={'project':'one','path':'plans/test.md','body':'stale','revision':hashlib.sha256(before).hexdigest()}).status_code==409


def test_cross_project_reply_rejected(workspace):
    c,h=signin(workspace[0]); cid=add(c,h).json['id']
    revision=c.get('/api/document?project=two&path=other.md').json['revision']
    assert c.post('/api/comments',headers=h,json={'project':'two','path':'other.md','revision':revision,'parent_id':cid,'body':'wrong'}).status_code==404


def test_invites_single_use_disable_reset(workspace):
    app,config,root=workspace;c,h=signin(app)
    response=c.post('/api/users',headers=h,json={'username':'colleague','name':'Colleague','projects':['one']})
    assert response.status_code==201
    token=response.json['token']; other=app.test_client()
    assert other.post('/api/activate',json={'token':token,'password':'short'}).status_code==400
    activate=other.post('/api/activate',json={'token':token,'password':'colleague-pass-123'})
    assert activate.status_code==200
    assert other.post('/api/activate',json={'token':token,'password':'colleague-pass-123'}).status_code==400
    uid=activate.json['user']['id']
    assert c.post(f'/api/users/{uid}',headers=h,json={'action':'disable'}).status_code==200
    assert other.get('/api/projects').status_code==401
    reset=c.post(f'/api/users/{uid}',headers=h,json={'action':'reset'})
    assert reset.status_code==200
    assert other.post('/api/activate',json={'token':reset.json['token'],'password':'new-password-123'}).status_code==200


def test_access_revocation_and_password_sessions(workspace):
    app,config,root=workspace; c,h=signin(app); reader,rh=signin(app,'reader')
    assert c.post('/api/users/2',headers=h,json={'action':'access','projects':[]}).status_code==200
    assert reader.get('/api/files?project=one').status_code==403
    another,ah=signin(app)
    changed=c.post('/api/password',headers=h,json={'current':'test-password-123','password':'new-password-123'})
    assert changed.status_code==200
    assert another.get('/api/projects').status_code==401


def test_export_symlink_rejected(workspace,tmp_path):
    app,config,root=workspace;c,h=signin(app)
    (root/'.reviews').symlink_to(tmp_path/'outside')
    assert c.post('/api/export',headers=h,json={'project':'one','path':'plans/test.md'}).status_code==403


def test_login_rate_limit(workspace):
    c=workspace[0].test_client()
    for _ in range(12):
        assert c.post('/api/login',json={'username':'unknown','password':'bad'}).status_code==401
    assert c.post('/api/login',json={'username':'unknown','password':'bad'}).status_code==429


def test_https_transport_policy(workspace):
    client=workspace[0].test_client()
    secure=client.get('/api/health',base_url='https://localhost')
    assert secure.headers['Strict-Transport-Security']=='max-age=31536000'
    assert 'Strict-Transport-Security' not in client.get('/api/health').headers
