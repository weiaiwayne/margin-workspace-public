import fcntl
import hashlib
import shutil
import subprocess
from pathlib import Path
import pytest
from app import render_document
from test_app import workspace,signin,add


def test_markdown_pdf_is_downloadable_and_preserves_source_and_comments(workspace,tmp_path):
    app,config,root=workspace;c,h=signin(app,'reader')
    source='# PDF heading\n\n**Bold text**, *italic* and <u>underline</u>. 中文 한글\n\n| Name | Status |\n| --- | --- |\n| Tables | Ready |\n\n```python\nprint("code block")\n```\n\n- List item\n'
    (root/'plans/test.md').write_text(source);assert add(c,h).status_code==201
    before=c.get('/api/comments?project=one&path=plans/test.md').json['comments']
    r=c.get('/api/markdown-pdf?project=one&path=plans/test.md')
    assert r.status_code==200 and r.mimetype=='application/pdf' and r.data.startswith(b'%PDF-')
    assert 'attachment;' in r.headers['Content-Disposition'] and 'test.pdf' in r.headers['Content-Disposition']
    assert r.headers['Cache-Control']=='no-store' and r.headers['X-Document-SHA256']==hashlib.sha256(source.encode()).hexdigest()
    assert (root/'plans/test.md').read_text()==source
    assert c.get('/api/comments?project=one&path=plans/test.md').json['comments']==before
    assert not list(root.rglob('*.pdf'))
    if shutil.which('pdftotext'):
        target=tmp_path/'export.pdf';target.write_bytes(r.data)
        text=subprocess.check_output(['pdftotext',str(target),'-'],text=True)
        for phrase in ['PDF heading','Bold text','Tables','Ready','code block','List item','中文','한글']:
            assert phrase in text


def test_pdf_scope_type_revision_and_render_failures(workspace,monkeypatch):
    app,config,root=workspace;c,h=signin(app,'reader');url='/api/markdown-pdf?project=one&path=plans/test.md'
    assert app.test_client().get(url).status_code==401
    outsider,_=signin(app,'outsider');assert outsider.get(url).status_code==403
    assert c.get('/api/markdown-pdf?project=two&path=other.md').status_code==403
    for path in ['../outside.md','linked.md','.secret.md']:
        assert c.get('/api/markdown-pdf',query_string={'project':'one','path':path}).status_code in (400,403)
    (root/'plans/note.txt').write_text('text');assert c.get('/api/markdown-pdf?project=one&path=plans/note.txt').status_code==400
    assert c.get(url+'&revision='+'0'*64).status_code==409
    with (Path(config['database']).parent/'pdf-export.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert c.get(url).status_code==503
    def fail(*args):raise subprocess.TimeoutExpired('pdf',45)
    monkeypatch.setattr('pdf_export.generate',fail);assert c.get(url).status_code==422
    (root/'plans/test.md').write_bytes(b'x'*(2*1024*1024+1));assert c.get(url).status_code==413


def test_pdf_cannot_embed_local_resources(tmp_path):
    import pdf_export
    secret=tmp_path/'secret.svg';secret.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="100"><text x="0" y="50">PRIVATE_FILE_MARKER</text></svg>')
    dangerous='<h1>Public heading</h1><img src="'+secret.as_uri()+'"><style>@import url("http://127.0.0.1:1/private");</style><a rel="attachment" href="'+secret.as_uri()+'">link</a>'
    cleaned=render_document(dangerous,'md');assert '<img' not in cleaned and '<style' not in cleaned and 'file:' not in cleaned and 'rel=' not in cleaned
    # Even an accidental future unsanitized image is blocked by the worker fetcher.
    pdf=pdf_export.generate('<h1>Public heading</h1><img src="'+secret.as_uri()+'">')
    if shutil.which('pdftotext'):
        output=tmp_path/'safe.pdf';output.write_bytes(pdf)
        text=subprocess.check_output(['pdftotext',str(output),'-'],text=True)
        assert 'Public heading' in text and 'PRIVATE_FILE_MARKER' not in text
