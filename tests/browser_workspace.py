"""Disposable end-to-end checks for uploads, folders, editing, PDFs and mobile."""
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from playwright.sync_api import sync_playwright,expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

def pdf_bytes():
    content=b'BT /F1 24 Tf 40 160 Td (Margin PDF preview works) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 240] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
    result=b'%PDF-1.4\n'; offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(result));result+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(result);result+=b'xref\n0 6\n0000000000 65535 f \n'
    for offset in offsets[1:]:result+=f'{offset:010d} 00000 n \n'.encode()
    return result+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'

with tempfile.TemporaryDirectory(prefix='margin-workspace-') as tmp:
    root=Path(tmp)/'project';root.mkdir();(root/'workspace').mkdir();(root/'plan.md').write_text('# Existing plan')
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(Path(tmp)/'db.sqlite'),'projects':{'test':{'root':str(root),'name':'Test','writable_directory':'workspace'}}}
    app=create_app(config);password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        uid=db.execute('INSERT INTO users(username,name,password) VALUES(?,?,?)',('reader','Reader',generate_password_hash(password))).lastrowid
        db.execute('INSERT INTO access VALUES(?,?)',(uid,'test'))
    server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.locator('#username').fill('reader');page.locator('#password').fill(password);page.locator('#login-submit').click()
            expect(page.locator('.file-row')).to_have_count(1)
            page.locator('#new-folder').click();page.locator('[name=name]').fill('Research');page.locator('#workspace-form button').click()
            expect(page.locator('#library-title')).to_have_text('workspace/Research')
            page.locator('#new-md').click();page.locator('#document-title').fill('notes.md');page.locator('#document-title').press('Enter');expect(page.locator('#document-title')).to_be_enabled();page.locator('#source-mode').click();page.locator('#document-source').fill('# Team notes\n\nPlease review this.');page.locator('#finish-editing').click()
            expect(page.locator('#document h1')).to_have_text('Team notes')
            page.locator('#comment-body').fill('Keep this through folder rename');page.locator('#post-button').click();expect(page.locator('.thread')).to_have_count(1)
            page.locator('#export-button').click();expect(page.locator('#export-state')).to_contain_text('Saved to project')
            page.locator('#edit-file').click();page.locator('#source-mode').click();page.locator('#document-source').fill('# Updated notes');page.locator('#finish-editing').click();expect(page.locator('#document h1')).to_have_text('Updated notes')
            # A concurrent disk edit must preserve the open editor draft.
            page.locator('#edit-file').click();page.locator('#source-mode').click();page.locator('#document-source').fill('My unsaved revision');(root/'workspace/Research/notes.md').write_text('# Concurrent update')
            page.locator('#save-document').click();expect(page.locator('#document-save-state')).to_contain_text('changed');expect(page.locator('#document-source')).to_have_value('My unsaved revision')
            page.on('dialog',lambda dialog:dialog.accept())
            page.locator('#back-button').click();page.locator('#folders [data-folder-path=\"workspace/Research\"]').click(button='right');page.get_by_role('menuitem',name='Rename…').click();page.locator('[name=name]').fill('Team');page.locator('#workspace-form button').click()
            expect(page.locator('#library-title')).to_have_text('workspace/Team')
            page.locator('.file-row').click();expect(page.locator('.thread')).to_contain_text('Keep this through folder rename');expect(page.locator('#export-state')).to_contain_text('not yet saved')
            page.locator('#back-button').click();page.locator('#new-txt').click();page.locator('#document-title').fill('plain.txt');page.locator('#document-title').press('Enter');expect(page.locator('#document-title')).to_be_enabled();page.locator('#document-source').fill('<b>not HTML</b>');page.locator('#finish-editing').click()
            expect(page.locator('#document')).to_have_text('<b>not HTML</b>');assert page.locator('#document b').count()==0
            page.locator('#back-button').click()
            page.locator('#file-upload').set_input_files([{'name':'preview.pdf','mimeType':'application/pdf','buffer':pdf_bytes()},{'name':'archive.zip','mimeType':'application/zip','buffer':b'PK-example'}])
            expect(page.locator('#upload-status')).to_contain_text('2 file(s) uploaded')
            page.locator('#file-upload').set_input_files({'name':'preview.pdf','mimeType':'application/pdf','buffer':pdf_bytes()})
            expect(page.locator('#upload-status')).to_contain_text('already exists')
            page.locator('.file-row').filter(has_text='preview.pdf').click();expect(page.locator('#pdf-status')).to_have_text('Page 1 of 1',timeout=20000)
            page.locator('#file-preview summary').click();expect(page.locator('.pdf-page-text')).to_contain_text('Margin PDF preview works')
            url=page.locator('#download-file').get_attribute('href').replace('api/download','api/pdf');response=page.request.get(f'http://127.0.0.1:{server.server_port}/'+url)
            assert response.status==200 and response.headers['content-type']=='application/pdf'
            expect(page.locator('#comments-toggle')).to_be_hidden()
            page.screenshot(path='/tmp/margin-pdf-preview.png')
            with page.expect_download() as download:page.locator('#download-file').click()
            assert download.value.suggested_filename=='preview.pdf'
            page.locator('#back-button').click();page.locator('.file-row').filter(has_text='archive.zip').click()
            expect(page.locator('#file-preview')).to_contain_text('Preview is not available')
            page.locator('#back-button').click();page.set_viewport_size({'width':390,'height':844})
            page.locator('#new-folder').click();page.locator('[name=name]').fill('Mobile');page.locator('#workspace-form button').click();expect(page.locator('#library-title')).to_have_text('workspace/Team/Mobile')
            page.screenshot(path='/tmp/margin-workspace-mobile.png')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.reload();expect(page.locator('#folders')).to_contain_text('workspace/Team/Mobile')
            assert not errors,errors
            browser.close();print('PASS: collaborative files, uploads, conflicts, nested folders, rename/comment preservation, PDF/download, text escaping and mobile.')
    finally:
        server.shutdown();thread.join()
