"""Real Linux ACL tests, including separate unprivileged agent identities."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest
import workspace_access as access
from app import create_app
from test_app import signin
from werkzeug.security import generate_password_hash

WRITER, READER, OUTSIDER = 42001, 42002, 42003

@pytest.fixture
def secured(monkeypatch):
    if os.geteuid()!=0 or not shutil.which('setfacl'):
        pytest.skip('Real ACL isolation check requires root and the acl package.')
    original=access.pwd.getpwnam
    monkeypatch.setattr(access.pwd,'getpwnam',lambda name:SimpleNamespace(pw_uid={'test-writer':WRITER,'test-reader':READER}[name]) if name in ('test-writer','test-reader') else original(name))
    with tempfile.TemporaryDirectory(prefix='margin-acl-') as temporary:
        base=Path(temporary);base.chmod(0o755)
        root=base/'workspace';root.mkdir();(root/'.reviews').mkdir()
        info={'name':'Private','root':str(root),'server_path':str(root),'writable_directory':'.','agent_access':{'test-writer':'write','test-reader':'read'}}
        access.reconcile(info,service_uid=os.geteuid())
        yield base,root,info


def as_user(uid, code, *paths):
    def drop():
        os.setgroups([]);os.setgid(uid);os.setuid(uid)
    return subprocess.run([sys.executable,'-c',code,*map(str,paths)],preexec_fn=drop,capture_output=True,text=True)


def readable(uid,path):
    return as_user(uid,'import pathlib,sys;pathlib.Path(sys.argv[1]).read_bytes()',path).returncode==0


def writable(uid,path):
    return as_user(uid,'import os,sys;fd=os.open(sys.argv[1],os.O_WRONLY|os.O_APPEND);os.close(fd)',path).returncode==0


def test_inherited_access_and_cross_workspace_denial(secured):
    base,root,info=secured
    old=os.umask(0o027)
    try:
        (root/'new').mkdir(mode=0o770)
        (root/'new/note.md').write_text('inherited')
        (root/'.reviews/new').mkdir(mode=0o770)
        (root/'.reviews/new/note.md.review.md').write_text('review')
    finally:os.umask(old)
    doc=root/'new/note.md';review=root/'.reviews/new/note.md.review.md'
    assert readable(WRITER,doc) and writable(WRITER,doc)
    assert readable(READER,doc) and not writable(READER,doc)
    assert readable(WRITER,review) and not writable(WRITER,review)
    assert readable(READER,review) and not writable(READER,review)
    assert not readable(OUTSIDER,doc) and not readable(OUTSIDER,review)
    other=base/'other';other.mkdir();(other/'secret.md').write_text('private')
    access.reconcile({**info,'root':str(other),'server_path':str(other),'agent_access':{}},service_uid=os.geteuid())
    assert not readable(WRITER,other/'secret.md')
    assert as_user(WRITER,'from pathlib import Path;import sys;Path(sys.argv[1]).write_text("agent edit")',root/'new/from-agent.md').returncode==0


def test_app_lifecycle_and_comment_exports_keep_agent_acl(secured):
    base,root,info=secured
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(base/'db'),'projects':{'one':info}}
    app=create_app(config)
    with sqlite3.connect(config['database']) as db:db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,1)',('admin','Admin',generate_password_hash('test-password-123')))
    c,h=signin(app)
    old=os.umask(0o027)
    try:
        for folder in ['nested','nested/deeper']:
            assert c.post('/api/folders',headers=h,json={'project':'one','path':folder}).status_code==201
        path='nested/deeper/plan.md'
        assert c.post('/api/text',headers=h,json={'project':'one','path':path,'content':'# Original'}).status_code==201
        assert readable(WRITER,root/path) and writable(WRITER,root/path)
        revision=c.get('/api/document',query_string={'project':'one','path':path}).json['revision']
        assert c.post('/api/comments',headers=h,json={'project':'one','path':path,'revision':revision,'body':'Please clarify.','quote':'Original'}).status_code==201
        for content in ['# Updated','# Updated again']:
            r=c.post('/api/text',headers=h,json={'project':'one','path':path,'content':content,'revision':revision});assert r.status_code==200
            revision=r.json['revision'];assert writable(WRITER,root/path)
            assert c.post('/api/export',headers=h,json={'project':'one','path':path}).status_code==200
            review=root/'.reviews'/ (path+'.review.md')
            assert readable(WRITER,review) and readable(READER,review)
            assert not writable(WRITER,review) and not readable(OUTSIDER,review)
            assert 'Please clarify.' in review.read_text()
        assert c.post('/api/upload',headers=h,data={'project':'one','folder':'nested/deeper','file':(io.BytesIO(b'uploaded'),'uploaded.txt')}).status_code==201
        assert writable(WRITER,root/'nested/deeper/uploaded.txt')
        assert c.post('/api/files/rename',headers=h,json={'project':'one','path':path,'new_path':'nested/deeper/renamed.md'}).status_code==200
        path='nested/deeper/renamed.md'
        tid=c.post('/api/trash',headers=h,json={'project':'one','path':path}).json['id']
        assert not readable(WRITER,root/'.margin-trash'/tid)
        assert c.post('/api/trash/restore',headers=h,json={'project':'one','id':tid}).status_code==200
        assert writable(WRITER,root/path) and not readable(OUTSIDER,root/path)
        assert len(c.get('/api/document',query_string={'project':'one','path':path}).json['comments'])==1
    finally:os.umask(old)


def test_repair_existing_permissions_ignores_links_and_secrets(secured):
    base,root,info=secured
    nested=root/'old';nested.mkdir(mode=0o700);doc=nested/'doc.md';doc.write_text('unchanged');doc.chmod(0o600)
    reviews=root/'.reviews/old';reviews.mkdir(mode=0o700);review=reviews/'doc.md.review.md';review.write_text('comment');review.chmod(0o600)
    outside=base/'outside';outside.mkdir();secret=outside/'secret';secret.write_text('secret');secret.chmod(0o600)
    (root/'link').symlink_to(outside);(root/'linked.md').symlink_to(secret)
    (root/'.env').write_text('hidden');(root/'.env').chmod(0o600)
    assert not readable(WRITER,review)
    before=hashlib.sha256(doc.read_bytes()+review.read_bytes()).hexdigest()
    access.reconcile(info,service_uid=os.geteuid());access.reconcile(info,service_uid=os.geteuid())
    assert readable(WRITER,doc) and writable(WRITER,doc) and readable(WRITER,review)
    assert not writable(WRITER,review) and not readable(OUTSIDER,review)
    assert before==hashlib.sha256(doc.read_bytes()+review.read_bytes()).hexdigest()
    assert secret.stat().st_mode&0o777==0o600 and not readable(WRITER,root/'.env')
    with pytest.raises(OSError):access.apply(root/'link/secret',info)
    (root/'hardlink.md').hardlink_to(secret)
    with pytest.raises(ValueError,match='multiply linked'):access.reconcile(info)
    assert secret.stat().st_mode&0o777==0o600


def test_imported_source_preserves_masked_rights_and_boundaries(secured):
    base,root,info=secured
    source=base/'source';source.mkdir();(source/'workspace').mkdir();(source/'.reviews').mkdir()
    doc=source/'plan.md';doc.write_text('plan')
    subprocess.run(['setfacl','-m',f'u:{OUTSIDER}:rw-,m::r--','--',str(doc)],check=True)
    before=doc.stat().st_uid
    access.reconcile({**info,'root':str(source),'server_path':str(source),'writable_directory':'workspace'},service_uid=os.geteuid())
    assert readable(WRITER,doc) and writable(WRITER,doc)
    assert readable(OUTSIDER,doc) and not writable(OUTSIDER,doc)
    assert doc.stat().st_uid==before
    assert not readable(OUTSIDER,source/'.reviews/no-file')
    acl=subprocess.run(['getfacl','-cpn',str(doc)],check=True,capture_output=True,text=True).stdout
    assert f'user:{OUTSIDER}:r--' in acl


def test_new_workspace_provisions_service_and_agent_inheritance(secured,monkeypatch):
    from workspace_broker import Broker
    base,root,info=secured
    mounts=base/'mounts';mounts.mkdir()
    run=subprocess.run
    monkeypatch.setattr(subprocess,'run',lambda args,**kwargs:SimpleNamespace(returncode=0) if args[0]=='systemd-run' else run(args,**kwargs))
    cfg={'registry':str(base/'registry.json'),'allowed_roots':[str(base)],'protected_paths':[],'new_folder_parent':str(base),'mount_root':str(mounts),'config_path':str(base/'broker.json'),'default_agent_access':info['agent_access']}
    broker=Broker(cfg);result=broker.provision({'name':'Fresh workspace','mode':'new','owner_id':1})
    created=broker.read_registry()[result['id']];new=Path(created['server_path'])
    assert created['agent_access']==info['agent_access']
    service=access.pwd.getpwnam('margin').pw_uid
    # Simulate the real unprivileged service creating content under its 0027 umask.
    code='import os,sys;from pathlib import Path;os.umask(0o027);p=Path(sys.argv[1]);(p/"subfolder").mkdir(mode=0o770);(p/"subfolder/new.md").write_text("new");(p/".reviews/new.review.md").write_text("review")'
    result=as_user(service,code,new);assert result.returncode==0,result.stderr
    assert readable(WRITER,new/'subfolder/new.md') and writable(WRITER,new/'subfolder/new.md')
    assert readable(WRITER,new/'.reviews/new.review.md') and not writable(WRITER,new/'.reviews/new.review.md')
    assert not readable(OUTSIDER,new/'subfolder/new.md')
