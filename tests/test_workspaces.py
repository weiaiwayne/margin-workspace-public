import io
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest
from test_app import workspace,signin
from workspace_broker import Broker,ProvisionError

@pytest.fixture
def personal(workspace,tmp_path):
    app,config,root=workspace
    folder=tmp_path/'personal';folder.mkdir();(folder/'note.md').write_text('# Private')
    (folder/'secret.pdf').write_bytes(b'%PDF-1.4\n%%EOF')
    registry=tmp_path/'registry.json'
    registry.write_text(json.dumps({'private':{'name':'Personal','root':str(folder),'server_path':str(folder),'reviews':str(folder/'.reviews'),'private':True,'owner_id':1,'writable_directory':'.','pending':False}}))
    config['workspace_registry']=str(registry)
    return app,config,folder,registry

def test_private_workspaces_never_leak_to_collaborators(personal):
    app,config,folder,registry=personal
    admin,ah=signin(app);reader,rh=signin(app,'reader')
    assert 'private' in [p['id'] for p in admin.get('/api/projects').json['projects']]
    assert [p['id'] for p in reader.get('/api/projects').json['projects']]==['one']
    # Even an accidentally inserted access grant cannot override private ownership.
    with sqlite3.connect(config['database']) as db:db.execute("INSERT INTO access VALUES(2,'private')")
    for route in ['files','document','comments','download','pdf','storage']:
        path='secret.pdf' if route=='pdf' else 'note.md'
        assert reader.get('/api/'+route,query_string={'project':'private','path':path}).status_code==403
    for route,body in [('text',{'path':'new.md','content':'No'}),('folders',{'path':'new'}),('folders/rename',{'path':'a','new_path':'b'}),('comments',{'path':'note.md','body':'No','revision':'a'*64}),('export',{'path':'note.md'})]:
        assert reader.post('/api/'+route,headers=rh,json={'project':'private',**body}).status_code==403
    assert reader.post('/api/upload',headers=rh,data={'project':'private','folder':'.','file':(io.BytesIO(b'No'),'note.txt')}).status_code==403
    assert reader.get('/api/server-folders?path=/root').status_code==403
    assert reader.post('/api/workspaces',headers=rh,json={'name':'No','mode':'new'}).status_code==403
    assert admin.post('/api/users/2',headers=ah,json={'action':'access','projects':['private']}).status_code==400
    assert admin.post('/api/users',headers=ah,json={'name':'New','username':'newuser','projects':['private']}).status_code==400
    assert [p['id'] for p in reader.get('/api/projects').json['projects']]==['one']

def test_owner_root_writes_registry_reload_and_pending(personal):
    app,config,folder,registry=personal;admin,headers=signin(app)
    assert admin.post('/api/text',headers=headers,json={'project':'private','path':'new.md','content':'# Works'}).status_code==201
    assert admin.post('/api/upload',headers=headers,data={'project':'private','folder':'.','file':(io.BytesIO(b'text'),'new.txt')}).status_code==201
    assert admin.post('/api/folders',headers=headers,json={'project':'private','path':'New Folder'}).status_code==201
    assert admin.post('/api/folders/rename',headers=headers,json={'project':'private','path':'New Folder','new_path':'Renamed'}).status_code==200
    assert admin.get('/api/files?project=private').json['writable_directory']=='.'
    r=json.loads(registry.read_text());r['private']['pending']=True;registry.write_text(json.dumps(r))
    assert admin.get('/api/files?project=private').status_code==503
    assert next(p for p in admin.get('/api/projects').json['projects'] if p['id']=='private')['pending']
    r['private']['owner_id']=999;registry.write_text(json.dumps(r))
    assert admin.get('/api/files?project=private').status_code==403

def test_root_cookie_replaces_legacy_cookie(workspace):
    app,config,_=workspace;config['base_path']='/'
    client=app.test_client();r=client.post('/api/login',json={'username':'admin','password':'test-password-123'})
    cookies=r.headers.getlist('Set-Cookie')
    assert any('Path=/docs/' in c and 'Max-Age=0' in c for c in cookies)
    assert any('Path=/;' in c for c in cookies)

@pytest.fixture
def broker(tmp_path,monkeypatch):
    base=tmp_path/'projects';base.mkdir();protected=base/'service';protected.mkdir();mounts=tmp_path/'mounts';mounts.mkdir()
    config={'allowed_roots':[str(base)],'protected_paths':[str(protected)],'existing_sources':[str(base/'existing')],'registry':str(tmp_path/'registry.json'),'new_folder_parent':str(base),'mount_root':str(mounts),'dropin':str(tmp_path/'unit.d/workspaces.conf'),'config_path':str(tmp_path/'broker.json'),'lock':str(tmp_path/'lock')}
    calls=[]
    monkeypatch.setattr('workspace_broker.subprocess.run',lambda args,**kwargs:calls.append(args))
    monkeypatch.setattr('workspace_broker.pwd.getpwnam',lambda name:SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid()))
    return Broker(config),base,calls

def test_broker_path_boundary(broker):
    b,base,calls=broker
    for path in ['/',str(base),str(base/'service'),str(base/'existing'),str(base/'existing/child'),str(base/'../escape'),str(base/'.ssh'),str(base/'bad:name')]:
        with pytest.raises(ProvisionError):b.path(path,attaching=True)
    (base/'linked').symlink_to(base/'service')
    with pytest.raises(ProvisionError):b.path(str(base/'linked'),attaching=True)
    assert b.browse('/')['folders']==[{'name':str(base),'path':str(base)}]
    assert all(f['name']!='service' for f in b.browse(str(base))['folders'])

def test_broker_new_and_existing_mounts(broker):
    b,base,calls=broker
    result=b.provision({'name':'My project','mode':'new','owner_id':1})
    info=b.read_registry()[result['id']]
    assert info['private'] and info['pending'] and info['writable_directory']=='.'
    assert (base/'my-project/.reviews').is_dir()
    b.activate(result['id'])
    assert not b.read_registry()[result['id']]['pending']
    assert 'BindPaths=' in Path(b.config['dropin']).read_text()
    existing=base/'Another project';existing.mkdir();(existing/'notes.md').write_text('# Keep me')
    second=b.provision({'name':'Existing','mode':'existing','owner_id':1,'path':str(existing)})
    b.activate(second['id'])
    assert (existing/'notes.md').read_text()=='# Keep me'
    assert (existing/'workspace').is_dir()
    dropin=Path(b.config['dropin']).read_text()
    assert 'BindReadOnlyPaths="'+str(existing)+'":' in dropin
    assert '.reviews' in dropin and 'workspace' in dropin
    with pytest.raises(ProvisionError):b.provision({'name':'Duplicate','mode':'existing','owner_id':1,'path':str(existing)})
