"""Markdown PDF downloads through desktop and mobile menus, using temporary data."""
import os,secrets,sqlite3,sys,tempfile,threading,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from playwright.sync_api import sync_playwright,expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

with tempfile.TemporaryDirectory(prefix='margin-pdf-browser-') as tmp:
    root=Path(tmp)/'project';root.mkdir();(root/'workspace').mkdir()
    source='# Export test\n\n**Bold**, *italic*, <u>underline</u>. 中文 한글\n\n| Item | Status |\n| --- | --- |\n| Table row | Ready |\n\n```python\nprint("code example")\n```\n'
    (root/'workspace/Plan α.md').write_text(source);(root/'workspace/plain.txt').write_text('plain')
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(Path(tmp)/'db'),'projects':{'test':{'root':str(root),'name':'PDF test','writable_directory':'workspace'}}}
    app=create_app(config);password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        uid=db.execute('INSERT INTO users(username,name,password) VALUES(?,?,?)',('reader','Reader',generate_password_hash(password))).lastrowid;db.execute('INSERT INTO access VALUES(?,?)',(uid,'test'))
    server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox']);context=browser.new_context(viewport={'width':1440,'height':1000},has_touch=True);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/');page.locator('#username').fill('reader');page.locator('#password').fill(password);page.locator('#login-submit').click()
            page.locator('.file-row').filter(has_text='plain.txt').click(button='right');expect(page.get_by_role('menuitem',name='Download as PDF')).to_have_count(0);page.keyboard.press('Escape')
            page.locator('.file-row').filter(has_text='Plan α.md').click(button='right')
            with page.expect_download(timeout=60000) as event:page.get_by_role('menuitem',name='Download as PDF').click()
            download=event.value;assert download.suggested_filename=='Plan α.pdf';download.save_as('/tmp/margin-pdf-desktop.pdf');assert Path('/tmp/margin-pdf-desktop.pdf').read_bytes().startswith(b'%PDF-');assert (root/'workspace/Plan α.md').read_text()==source
            text=subprocess.check_output(['pdftotext','/tmp/margin-pdf-desktop.pdf','-'],text=True);assert 'Table row' in text and 'code example' in text and '中文' in text
            page.set_viewport_size({'width':390,'height':844});page.locator('#file-list').get_by_role('button',name='Actions for Plan α.md',exact=True).tap()
            with page.expect_download(timeout=60000) as event:page.get_by_role('menuitem',name='Download as PDF').tap()
            assert event.value.suggested_filename=='Plan α.pdf'
            page.locator('.file-row').filter(has_text='Plan α.md').tap();page.locator('#edit-file').tap();page.locator('.tiptap').fill('Newest unsaved PDF text')
            page.locator('#document-more').tap()
            with page.expect_download(timeout=60000) as event:page.get_by_role('menuitem',name='Download as PDF').tap()
            event.value.save_as('/tmp/margin-pdf-mobile.pdf');text=subprocess.check_output(['pdftotext','/tmp/margin-pdf-mobile.pdf','-'],text=True);assert 'Newest unsaved PDF text' in text and 'Newest unsaved PDF text' in (root/'workspace/Plan α.md').read_text()
            assert not list(root.rglob('*.pdf'));assert not errors,errors;browser.close();print('PASS: real desktop/mobile PDF downloads, Unicode filenames/text, tables/code, TXT exclusion, saving current edits and no workspace PDF artifacts.')
    finally:server.shutdown();thread.join()
