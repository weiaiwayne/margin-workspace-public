import io
import sqlite3
from pathlib import Path
import pytest
from test_app import workspace, signin, add

@pytest.fixture
def writable(workspace):
    app,config,root=workspace
    config['projects']['one']['writable_directory']='workspace'
    (root/'workspace').mkdir()
    return app,config,root

def create(client,headers,path='workspace/hello.md',content='# Hello'):
    return client.post('/api/text',headers=headers,json={'project':'one','path':path,'content':content})

def upload(client,headers,path='sample.txt',body=b'Hello',folder='workspace',project='one'):
    return client.post('/api/upload',headers=headers,data={'project':project,'folder':folder,'file':(io.BytesIO(body),path)})

def test_collaborator_create_edit_and_conflict(writable):
    app,_,root=writable;c,h=signin(app,'reader')
    r=create(c,h,content=' # Hello\n\n  whitespace  \n');assert r.status_code==201
    assert (root/'workspace/hello.md').read_text()==' # Hello\n\n  whitespace  \n'
    assert create(c,h).status_code==409
    revision=r.json['revision']
    result=c.post('/api/text',headers=h,json={'project':'one','path':'workspace/hello.md','content':'Updated','revision':revision})
    assert result.status_code==200
    assert c.post('/api/text',headers=h,json={'project':'one','path':'workspace/hello.md','content':'Overwrite','revision':revision}).status_code==409
    assert (root/'workspace/hello.md').read_text()=='Updated'
    assert create(c,h,'plans/test.md').status_code==403
    assert create(c,h,'workspace/bad.html').status_code==400

@pytest.mark.parametrize('path',['workspace/../escape.md','workspace//escape.md','workspace/.hidden.md','workspace/a/../../escape.md','/workspace/x.md','workspace/evil\\x.md','workspace/.git/config.md','workspace/bad\x00.md','workspace/bad.review.md'])
def test_write_paths_rejected(writable,path):
    c,h=signin(writable[0],'reader');assert create(c,h,path).status_code in (400,403)

def test_upload_read_download_and_permissions(writable):
    app,_,root=writable;c,h=signin(app,'reader')
    assert upload(c,h).status_code==201
    assert upload(c,h).status_code==409
    assert upload(c,h,'payload.html',b'<script>alert(1)</script>').status_code==201
    response=c.get('/api/download?project=one&path=workspace/payload.html')
    assert response.status_code==200
    assert response.mimetype=='application/octet-stream'
    assert 'attachment' in response.headers['Content-Disposition']
    assert 'sandbox' in response.headers['Content-Security-Policy']
    assert c.get('/api/document?project=one&path=workspace/payload.html').status_code==400
    listing=c.get('/api/files?project=one').json
    assert {'path':'workspace','writable':False} in listing['folders']
    assert any(f['path']=='workspace/sample.txt' and f['kind']=='txt' for f in listing['files'])
    stranger,sh=signin(app,'outsider')
    assert upload(stranger,sh).status_code==403
    assert stranger.get('/api/download?project=one&path=workspace/sample.txt').status_code==403
    assert app.test_client().get('/api/download?project=one&path=workspace/sample.txt').status_code==401
    assert c.post('/api/upload',data={}).status_code==403
    assert upload(c,h,project='two').status_code==403
    assert upload(c,h,'../oops.md').status_code==400
    assert upload(c,h,folder='plans').status_code==403
    (root/'workspace/link').symlink_to(root/'plans',target_is_directory=True)
    assert create(c,h,'workspace/link/test.md').status_code==403


def test_folders_rename_preserves_comments_and_exports(writable):
    app,_,root=writable;c,h=signin(app,'reader')
    def folder(path):return c.post('/api/folders',headers=h,json={'project':'one','path':path})
    assert folder('workspace/Review_100%').status_code==201
    assert folder('workspace/Review_100%').status_code==409
    assert folder('workspace/Review_100%/Nested').status_code==201
    path='workspace/Review_100%/Nested/doc.md'
    assert create(c,h,path).status_code==201
    revision=c.get('/api/document',query_string={'project':'one','path':path}).json['revision']
    assert c.post('/api/comments',headers=h,json={'project':'one','path':path,'body':'Keep this comment','revision':revision}).status_code==201
    assert c.post('/api/export',headers=h,json={'project':'one','path':path}).status_code==200
    r=c.post('/api/folders/rename',headers=h,json={'project':'one','path':'workspace/Review_100%','new_path':'workspace/Renamed'})
    assert r.status_code==200
    new='workspace/Renamed/Nested/doc.md'
    result=c.get('/api/comments',query_string={'project':'one','path':new})
    assert result.json['comments'][0]['body']=='Keep this comment'
    assert result.json['export']['dirty']
    assert (root/'.reviews'/f'{path}.review.md').exists()
    assert c.post('/api/export',headers=h,json={'project':'one','path':new}).status_code==200
    assert (root/'.reviews'/f'{new}.review.md').exists()
    for old,new in [('workspace','another'),('plans','workspace/plans'),('workspace/Renamed','workspace/Renamed/child')]:
        assert c.post('/api/folders/rename',headers=h,json={'project':'one','path':old,'new_path':new}).status_code in (400,403)
    assert folder('workspace/Empty').status_code==201
    assert any(f['path']=='workspace/Empty' for f in c.get('/api/files?project=one').json['folders'])


def test_pdf_and_plain_text(writable):
    app,_,_=writable;c,h=signin(app,'reader')
    assert upload(c,h,'bad.pdf',b'not PDF').status_code==400
    pdf=b'%PDF-1.4\n%%EOF'
    assert upload(c,h,'sample.pdf',pdf).status_code==201
    response=c.get('/api/pdf?project=one&path=workspace/sample.pdf')
    assert response.status_code==200 and response.mimetype=='application/pdf'
    assert response.headers['X-Frame-Options']=='DENY'
    assert app.test_client().get('/api/pdf?project=one&path=workspace/sample.pdf').status_code==401
    assert create(c,h,'workspace/plain.txt','<script>evil()</script>\n# plain text').status_code==201
    response=c.get('/api/document?project=one&path=workspace/plain.txt')
    assert '<script>' not in response.json['html'] and '&lt;script&gt;' in response.json['html']
    assert '<h1' not in response.json['html']
    assert c.get('/api/pdf?project=one&path=workspace/plain.txt').status_code==400


def test_quota_and_large_upload(writable):
    app,config,root=writable;c,h=signin(app,'reader')
    config['projects']['one']['storage_limit_bytes']=8
    assert upload(c,h,body=b'12345678').status_code==201
    assert upload(c,h,'more.txt',b'1').status_code==413
    assert create(c,h).status_code==413
    config['projects']['one']['storage_limit_bytes']=1024*1024*1024
    assert upload(c,h,'huge.bin',b'x'*(32*1024*1024)).status_code==201
    assert (root/'workspace/huge.bin').stat().st_size==32*1024*1024
    assert not list((root/'workspace').glob('.upload-*'))


def test_streamed_text_validation_and_failed_upload_cleanup(writable):
    app,config,root=writable;c,h=signin(app,'reader')
    text=b'x'*(1024*1024-1)+'€'.encode()+b'end'
    assert upload(c,h,'boundary.txt',text).status_code==201
    assert (root/'workspace/boundary.txt').read_bytes()==text
    assert upload(c,h,'incomplete.txt',b'x'*(1024*1024)+b'\xe2').status_code==400
    assert upload(c,h,'empty.pdf',b'').status_code==400
    config['projects']['one']['storage_limit_bytes']=len(text)+1024*1024+1
    assert upload(c,h,'too-big.bin',b'x'*(1024*1024+2)).status_code==413
    assert not (root/'workspace/too-big.bin').exists()
    assert not (root/'workspace/incomplete.txt').exists()
    assert not list((root/'workspace').glob('.upload-*'))


def test_upload_query_permissions_and_request_bounds(writable):
    app,config,root=writable;c,h=signin(app,'reader')
    assert c.post('/api/upload?project=two',headers=h,data=b'x'*100).status_code==403
    body={'project':'one','folder':'workspace','file':(io.BytesIO(b'works'),'query.txt')}
    assert c.post('/api/upload?project=one',headers=h,data=body).status_code==201
    body={'project':'two','folder':'workspace','file':(io.BytesIO(b'no'),'wrong.txt')}
    assert c.post('/api/upload?project=one',headers=h,data=body).status_code==400
    config['projects']['one']['storage_limit_bytes']=5
    assert c.post('/api/upload?project=one',headers=h,data=b'x'*(1024*1024+1)).status_code==413
    assert c.post('/api/text',headers=h,data=b'x'*(3*1024*1024+1)).status_code==413
    assert app.test_client().post('/api/upload',data=b'x'*(4*1024*1024)).status_code==401
