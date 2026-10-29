"""Touch-first workflows against a disposable workspace, without production data."""
import os,secrets,sqlite3,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from playwright.sync_api import sync_playwright,expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

with tempfile.TemporaryDirectory(prefix='margin-mobile-') as tmp:
    root=Path(tmp)/'project';root.mkdir();(root/'workspace').mkdir()
    (root/'workspace/note.md').write_text('# Mobile review\n\nA passage to discuss.\n\n'+('\n\nMore document text.'*30))
    (root/'workspace/plain.txt').write_text('Plain text\n')
    (root/'protected.md').write_text('# Protected source')
    for i in range(30):(root/'workspace'/f'Folder {i:02}').mkdir()
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(Path(tmp)/'db'),'projects':{'test':{'root':str(root),'name':'A project with a long name for mobile navigation','writable_directory':'workspace'}}}
    app=create_app(config);password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        uid=db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,1)',('reader','Reader',generate_password_hash(password))).lastrowid;db.execute('INSERT INTO access VALUES(?,?)',(uid,'test'))
    server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox']);context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=2);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/');page.locator('#username').fill('reader');page.locator('#password').fill(password);page.locator('#login-submit').tap();expect(page.locator('#storage-summary')).to_contain_text('used')
            for width,height in [(320,640),(390,844),(820,1180),(844,390)]:
                page.set_viewport_size({'width':width,'height':height});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('#menu-button').tap();expect(page.locator('#menu-button')).to_have_attribute('aria-expanded','true');assert page.locator('.main').evaluate('(e)=>e.inert')
                nav=page.locator('.sidebar-navigation');nav.evaluate('(e)=>e.scrollTop=e.scrollHeight');expect(page.locator('#folders [data-folder-path="workspace/Folder 29"]')).to_be_in_viewport();expect(page.locator('#sidebar .app-footer')).to_be_in_viewport()
                page.locator('#sidebar-backdrop').tap(position={'x':width-15,'y':30});expect(page.locator('#sidebar')).to_be_hidden();assert not page.locator('.main').evaluate('(e)=>e.inert')
            page.set_viewport_size({'width':390,'height':844});page.locator('#menu-button').tap();page.keyboard.press('Escape');expect(page.locator('#menu-button')).to_be_focused()
            # Touch menu on a protected source must not offer rename/delete.
            page.locator('#file-list').get_by_role('button',name='Actions for protected.md',exact=True).tap();expect(page.get_by_role('menuitem',name='Rename…')).to_have_count(0);page.keyboard.press('Escape')
            page.locator('#file-list').get_by_role('button',name='Actions for note.md',exact=True).tap();page.get_by_role('menuitem',name='Rename…').tap();page.locator('[name=name]').fill('phone.md');page.locator('#workspace-form button').tap();expect(page.locator('#document-title')).to_have_value('phone.md')
            page.locator('#edit-file').tap();editor=page.locator('.tiptap');editor.fill('Written on a phone');editor.select_text();page.get_by_role('button',name='Bold',exact=True).tap();expect(page.locator('.tiptap strong')).to_have_text('Written on a phone')
            for width,height in [(320,640),(390,500),(820,1180),(844,390)]:
                page.set_viewport_size({'width':width,'height':height});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert page.locator('.reading-area').bounding_box()['height']>=75;expect(page.locator('#save-document')).to_be_in_viewport();expect(page.locator('#finish-editing')).to_be_in_viewport()
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/margin-mobile-editor.png');page.locator('#finish-editing').tap();expect(page.locator('.tiptap')).to_have_count(0);assert '**Written on a phone**' in (root/'workspace/phone.md').read_text()
            # Highlight/comment, close with an unsent draft, reopen and post.
            page.locator('#document strong').select_text();expect(page.locator('#selection-comment')).to_be_visible();page.locator('#selection-comment').tap();expect(page.locator('#comments-panel')).to_be_visible();page.locator('#comment-body').fill('Keep the mobile comment.');page.locator('#close-comments').tap();page.locator('#comments-toggle').tap();expect(page.locator('#comment-body')).to_have_value('Keep the mobile comment.');page.locator('#post-button').tap();expect(page.locator('.thread')).to_have_count(1)
            page.locator('#save-comments-mobile').tap();expect(page.locator('#export-state')).to_contain_text('Saved to project');assert 'Keep the mobile comment.' in (root/'.reviews/workspace/phone.md.review.md').read_text()
            page.locator('.thread-quote').tap();expect(page.locator('#comments-panel')).to_be_hidden();expect(page.locator('mark.comment-highlight')).to_have_text('Written on a phone')
            # Less frequent document actions stay reachable without crowding the reader.
            page.locator('#document-more').tap();page.get_by_role('menuitem',name='History',exact=True).tap();expect(page.locator('.history-row')).to_have_count(1);page.locator('#close-modal').tap()
            page.locator('#back-button').tap();page.locator('#new-md').tap();expect(page.locator('.tiptap')).to_be_visible();page.locator('.tiptap').fill('New from phone');page.locator('#finish-editing').tap();page.locator('#back-button').tap();page.locator('.file-row').filter(has_text='plain.txt').tap();page.locator('#edit-file').tap();page.locator('#document-source').fill('Phone text\n');page.locator('#finish-editing').tap();expect(page.locator('#document-source')).to_have_count(0);assert (root/'workspace/plain.txt').read_text()=='Phone text\n'
            page.locator('#back-button').tap();page.locator('#file-upload').set_input_files({'name':'phone-upload.txt','mimeType':'text/plain','buffer':b'phone upload'});expect(page.locator('.file-row').filter(has_text='phone-upload.txt')).to_have_count(1)
            # Sidebar folder touch actions, rename, Trash and recovery.
            page.locator('#menu-button').tap();page.locator('#folders').get_by_role('button',name='Actions for workspace/Folder 00',exact=True).tap();page.get_by_role('menuitem',name='Rename…').tap();page.locator('[name=name]').fill('Phone folder');page.locator('#workspace-form button').tap();expect(page.locator('#library-title')).to_have_text('workspace/Phone folder')
            page.locator('#menu-button').tap();page.locator('#folders').get_by_role('button',name='Actions for workspace/Phone folder',exact=True).tap();page.once('dialog',lambda d:d.accept());page.get_by_role('menuitem',name='Move to Trash').tap();expect(page.locator('#library-title')).to_have_text('All documents');page.locator('#view-trash').tap();page.locator('.trash-row button').tap();expect(page.locator('.trash-row')).to_have_count(0);page.locator('#close-modal').tap();assert (root/'workspace/Phone folder').is_dir()
            page.locator('#menu-button').tap();page.locator('#folders [data-folder-path="workspace"]').tap();expect(page.locator('.folder-entry').first.locator('.item-menu-button')).to_be_visible();page.screenshot(path='/tmp/margin-mobile-library.png')
            assert not errors,errors;browser.close();print('PASS: phone/tablet/landscape layout, touch file/folder actions, drawer dismissal, editing, formatting, comment drafts/anchors/export, history, new documents, TXT, upload, Trash/restore and protected source boundaries.')
    finally:server.shutdown();thread.join()
