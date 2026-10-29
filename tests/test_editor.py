import sqlite3
from pathlib import Path
import pytest
from test_app import workspace,signin,add

@pytest.fixture
def managed(workspace):
    app,cfg,root=workspace;cfg['projects']['one']['writable_directory']='workspace';(root/'workspace').mkdir();(root/'workspace/a.md').write_text('# Original')
    return app,cfg,root

def test_save_history_and_access(managed):
    app,cfg,root=managed;c,h=signin(app,'reader');url='/api/document?project=one&path=workspace/a.md';rev=c.get(url).json['revision']
    assert c.post('/api/text',headers=h,json={'project':'one','path':'workspace/a.md','revision':rev,'content':'# Edited'}).status_code==200
    history=c.get('/api/versions?project=one&path=workspace/a.md').json['versions'];assert len(history)==1
    assert c.get('/api/versions/'+str(history[0]['id'])).json['content']=='# Original'
    other,oh=signin(app,'outsider');assert other.get('/api/versions/'+str(history[0]['id'])).status_code==403
    assert c.post('/api/text',headers=h,json={'project':'one','path':'workspace/a.md','revision':rev,'content':'stale'}).status_code==409
    assert (root/'workspace/a.md').read_text()=='# Edited'

def test_rename_trash_restore_comments_and_history(managed):
    app,cfg,root=managed;c,h=signin(app,'reader');path='workspace/a.md';rev=c.get('/api/document?project=one&path='+path).json['revision']
    c.post('/api/comments',headers=h,json={'project':'one','path':path,'revision':rev,'body':'Retain me','quote':'Original'})
    c.post('/api/text',headers=h,json={'project':'one','path':path,'revision':rev,'content':'# New'})
    c.post('/api/export',headers=h,json={'project':'one','path':path})
    result=c.post('/api/files/rename',headers=h,json={'project':'one','path':path,'new_path':'workspace/b.md'});assert result.status_code==200
    path='workspace/b.md';result=c.post('/api/trash',headers=h,json={'project':'one','path':path});assert result.status_code==200;tid=result.json['id']
    assert not (root/path).exists();assert c.get('/api/document?project=one&path='+path).status_code==404
    assert c.get('/api/trash?project=one').json['items'][0]['path']==path
    outsider,oh=signin(app,'outsider');assert outsider.post('/api/trash/restore',headers=oh,json={'project':'one','id':tid}).status_code==403
    (root/path).write_text('New occupant');assert c.post('/api/trash/restore',headers=h,json={'project':'one','id':tid}).status_code==409;(root/path).unlink()
    assert c.post('/api/trash/restore',headers=h,json={'project':'one','id':tid}).status_code==200
    doc=c.get('/api/document?project=one&path='+path).json;assert doc['comments'][0]['body']=='Retain me';assert doc['export']['dirty'];assert c.get('/api/versions?project=one&path='+path).json['versions']
    assert (root/'.reviews/workspace/a.md.review.md').exists()

def test_file_management_scope_and_symlinks(managed):
    app,cfg,root=managed;c,h=signin(app,'reader')
    for path in ['plans/test.md','workspace','../outside.md','workspace/../plans','linked.md']:
        assert c.post('/api/trash',headers=h,json={'project':'one','path':path}).status_code in (400,403)
    assert c.post('/api/files/rename',headers=h,json={'project':'one','path':'workspace/a.md','new_path':'workspace/a.py'}).status_code==400
    (root/'workspace/link').symlink_to(root/'plans',target_is_directory=True)
    assert c.post('/api/trash',headers=h,json={'project':'one','path':'workspace/link'}).status_code==403
    assert c.post('/api/trash',json={'project':'one','path':'workspace/a.md'}).status_code==403

def test_folder_trash_roundtrip(managed):
    app,cfg,root=managed;c,h=signin(app,'reader');(root/'workspace/folder').mkdir();(root/'workspace/folder/nested.txt').write_text('nested')
    tid=c.post('/api/trash',headers=h,json={'project':'one','path':'workspace/folder'}).json['id']
    assert not (root/'workspace/folder').exists();assert c.post('/api/trash/restore',headers=h,json={'project':'one','id':tid}).status_code==200;assert (root/'workspace/folder/nested.txt').read_text()=='nested'

def test_broker_document_scope_recovery_and_conflict(tmp_path,monkeypatch):
    import hashlib,os
    from types import SimpleNamespace
    from workspace_broker import Broker,ProvisionError
    root=tmp_path/'source';root.mkdir();target=root/'plan.md';target.write_text('# Before');target.chmod(0o640)
    outside=tmp_path/'outside.md';outside.write_text('Secret');(root/'linked.md').symlink_to(outside);(root/'.hidden.md').write_text('Hidden')
    cfg={'allowed_roots':[str(root)],'protected_paths':[],'registry':str(tmp_path/'registry'),'document_sources':{'one':str(root)},'document_history':str(tmp_path/'history')}
    b=Broker(cfg);monkeypatch.setattr('workspace_broker.subprocess.run',lambda *args,**kwargs:SimpleNamespace(stdout=b''))
    old=hashlib.sha256(b'# Before').hexdigest();payload={'project':'one','path':'plan.md','revision':old,'content':'# After'}
    for path in ['../outside.md','linked.md','.hidden.md','foo.py','plan.md.review.md','new.md']:
        with pytest.raises(ProvisionError):b.save_document({**payload,'path':path})
    with pytest.raises(ProvisionError):b.save_document({**payload,'project':'unknown'})
    result=b.save_document(payload);assert target.read_text()=='# After';assert result['revision']==hashlib.sha256(b'# After').hexdigest();assert next((tmp_path/'history').iterdir()).read_text()=='# Before';assert target.stat().st_mode & 0o777==0o640
    with pytest.raises(ProvisionError):b.save_document(payload)
    assert outside.read_text()=='Secret'

def test_underline_renders_without_html_attributes(managed):
    app,config,root=managed
    (root/'workspace/a.md').write_text('<u onclick="alert(1)">**Bold** and *italic* underline</u>')
    client,headers=signin(app,'reader')
    html=client.get('/api/document?project=one&path=workspace/a.md').json['html']
    assert '<u>' in html and '<strong>Bold</strong>' in html and '<em>italic</em>' in html
    assert 'onclick' not in html

def test_storage_usage_and_trash_are_project_scoped(managed):
    app,config,root=managed;c,h=signin(app,'reader')
    (root/'workspace/data.txt').write_bytes(b'x'*4096)
    (root/'workspace/symlink.txt').symlink_to(root/'plans/test.md')
    usage=c.get('/api/storage?project=one').json
    assert usage['used_bytes']==len(b'# Original')+4096 and usage['trash_bytes']==0
    assert usage['available_bytes']==usage['limit_bytes']-usage['used_bytes']
    tid=c.post('/api/trash',headers=h,json={'project':'one','path':'workspace/data.txt'}).json['id']
    after=c.get('/api/storage?project=one').json
    assert after['used_bytes']==usage['used_bytes'] and after['trash_bytes']==4096
    c.post('/api/trash/restore',headers=h,json={'project':'one','id':tid})
    assert c.get('/api/storage?project=one').json['trash_bytes']==0
    assert c.get('/api/storage?project=two').status_code==403
    assert app.test_client().get('/api/storage?project=one').status_code==401
    config['projects']['one']['storage_limit_bytes']=100
    assert c.get('/api/storage?project=one').json['available_bytes']==0
    admin,ah=signin(app,'admin');assert admin.get('/api/storage?project=two').json=={'enabled':False}
