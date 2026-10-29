"""New-document canvas, inline title and Markdown toolbar persistence."""
import os,secrets,sqlite3,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from playwright.sync_api import sync_playwright,expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
with tempfile.TemporaryDirectory(prefix='margin-new-doc-') as tmp:
    root=Path(tmp)/'project';root.mkdir();(root/'workspace').mkdir();(root/'workspace/Untitled document.md').write_text('# Already exists')
    for i in range(45):(root/'workspace'/f'Folder {i:02}').mkdir()
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(Path(tmp)/'db.sqlite'),'projects':{'test':{'root':str(root),'name':'Test','writable_directory':'workspace'}}}
    app=create_app(config);password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        uid=db.execute('INSERT INTO users(username,name,password) VALUES(?,?,?)',('reader','Reader',generate_password_hash(password))).lastrowid;db.execute('INSERT INTO access VALUES(?,?)',(uid,'test'))
    server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox']);page=browser.new_page(viewport={'width':1500,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url);page.locator('#username').fill('reader');page.locator('#password').fill(password);page.locator('#login-submit').click();page.locator('#new-md').click()
            expect(page.locator('#modal')).not_to_be_visible();expect(page.locator('.tiptap')).to_be_focused();expect(page.locator('#document-title')).to_have_value('Untitled document 2.md');expect(page.get_by_role('button',name='Underline',exact=True)).to_be_visible()
            page.keyboard.type('Formatted words');page.keyboard.press('Control+a')
            assert page.evaluate('getSelection().toString()')=='Formatted words', page.evaluate('({selection:getSelection().toString(),active:document.activeElement.outerHTML})')
            for label in ['Bold','Italic','Underline']:
                page.get_by_role('button',name=label,exact=True).click()
                expect(page.locator('.tiptap '+{'Bold':'strong','Italic':'em','Underline':'u'}[label])).to_have_text('Formatted words')
            expect(page.locator('.tiptap strong')).to_have_text('Formatted words');expect(page.locator('.tiptap em')).to_have_text('Formatted words');expect(page.locator('.tiptap u')).to_have_text('Formatted words')
            # Rename in place without disturbing the editor draft.
            page.locator('#document-title').fill('Project notes');page.locator('#document-title').press('Enter');expect(page.locator('#document-title')).to_have_value('Project notes.md');expect(page.locator('.tiptap u')).to_have_text('Formatted words')
            page.locator('#finish-editing').click();expect(page.locator('.tiptap')).to_have_count(0);expect(page.locator('#document u')).to_have_text('Formatted words');expect(page.locator('#document strong')).to_have_text('Formatted words');expect(page.locator('#document em')).to_have_text('Formatted words')
            assert '<u>' in (root/'workspace/Project notes.md').read_text();assert (root/'workspace/Untitled document.md').read_text()=='# Already exists'
            page.locator('#edit-file').click();expect(page.locator('.tiptap u')).to_have_text('Formatted words');expect(page.locator('#document-source')).to_have_count(0)
            page.locator('#comment-body').fill('Keep this thread with the title.');page.locator('#post-button').click();expect(page.locator('.thread')).to_have_count(1)
            page.locator('#document-title').fill('Renamed notes.md');page.locator('#document-title').press('Enter');expect(page.locator('#document-name')).to_have_text('Renamed notes.md');expect(page.locator('.thread')).to_contain_text('Keep this thread')
            page.locator('#document-title').fill('Untitled document.md');page.locator('#document-title').press('Enter');expect(page.locator('#toast')).to_contain_text('already exists');page.locator('#document-title').press('Escape');expect(page.locator('#document-title')).to_have_value('Renamed notes.md')
            page.screenshot(path='/tmp/margin-new-document.png');page.locator('#back-button').click();page.locator('#new-txt').click();expect(page.locator('#document-source')).to_be_focused();expect(page.locator('#format-controls')).not_to_be_visible();page.locator('#document-source').fill('Text with <u>literal markup</u>\n  spaces');page.locator('#finish-editing').click();expect(page.locator('#document-source')).to_have_count(0);expect(page.locator('#document')).to_have_text('Text with <u>literal markup</u>\n  spaces');assert page.locator('#document u').count()==0
            page.locator('#back-button').click();page.set_viewport_size({'width':390,'height':844});page.locator('#new-md').click();expect(page.locator('.tiptap')).to_be_visible();expect(page.get_by_role('button',name='Underline',exact=True)).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path='/tmp/margin-new-document-mobile.png')
            page.locator('#back-button').click();page.locator('#new-folder').click();page.locator('[name=name]').fill('Folder actions');page.locator('#workspace-form button').click();expect(page.locator('#library-title')).to_have_text('workspace/Folder actions')
            folder=page.locator('#folders [data-folder-path="workspace/Folder actions"]');page.locator('#menu-button').click();folder.focus();folder.press('Shift+F10');expect(page.get_by_role('menu',name='Folder actions')).to_be_visible();page.get_by_role('menuitem',name='Rename…').click();page.locator('[name=name]').fill('Renamed folder');page.locator('#workspace-form button').click();expect(page.locator('#library-title')).to_have_text('workspace/Renamed folder')
            page.locator('#menu-button').click();page.locator('#folders [data-folder-path="workspace/Renamed folder"]').click(button='right');page.once('dialog',lambda dialog:dialog.accept());page.get_by_role('menuitem',name='Move to Trash').click();expect(page.locator('#library-title')).to_have_text('All documents');assert not (root/'workspace/Renamed folder').exists()
            page.locator('#view-trash').click();page.locator('.trash-row button').click();expect(page.locator('.trash-row')).to_have_count(0);page.locator('#close-modal').click();assert (root/'workspace/Renamed folder').is_dir()
            page.set_viewport_size({'width':1500,'height':1000});page.locator('#folders [data-folder-path="workspace"]').click(button='right');expect(page.get_by_role('menuitem',name='Rename…')).to_have_count(0);page.get_by_role('menuitem',name='Open folder').click();page.locator('.folder-card').filter(has_text='Renamed folder').click(button='right');expect(page.get_by_role('menuitem',name='Rename…')).to_be_visible();page.keyboard.press('Escape');expect(page.get_by_role('menu',name='Folder actions')).not_to_be_visible()
            assert not errors,errors;browser.close();print('PASS: direct new Markdown/text editor, inline naming, collision protection, bold/italic/underline roundtrip, comment preservation and mobile toolbar.')
    finally:server.shutdown();thread.join()
