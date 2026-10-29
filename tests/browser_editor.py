"""Document editing, revision conflicts, review handoffs and recoverable file management."""
import json,re,os,secrets,sqlite3,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from workspace_broker import Broker,Handler,Server
from playwright.sync_api import sync_playwright,expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

with tempfile.TemporaryDirectory(prefix='margin-editor-') as tmp:
    base=Path(tmp);root=base/'project';root.mkdir();(root/'workspace').mkdir()
    source='# Building plan\n\nA passage to discuss.\n\n- Keep lists\n\n| Item | Status |\n| --- | --- |\n| Test | Open |\n\n```python\nprint("safe")\n```\n'
    (root/'plan.md').write_text(source)
    (root/'workspace/notes.md').write_text('# Team notes\n\nOriginal paragraph.')
    (root/'workspace/plain.txt').write_text('<b>Plain text</b>\n\n  spaces\n')
    (root/'workspace/advanced.md').write_text('---\ntitle: Metadata\n---\n\n# Heading\n\nText[^1]\n\n[^1]: Footnote\n')
    cfg={'registry':str(base/'registry.json'),'lock':str(base/'lock'),'allowed_roots':[str(base)],'protected_paths':[],'document_sources':{'test':str(root)},'document_history':str(base/'history')}
    broker=Server(str(base/'broker.sock'),Handler);broker.broker=Broker(cfg);bt=threading.Thread(target=broker.serve_forever,daemon=True);bt.start()
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(base/'db.sqlite'),'workspace_broker_socket':str(base/'broker.sock'),'edit_project_documents':True,'projects':{'test':{'root':str(root),'server_path':str(root),'name':'Test','writable_directory':'workspace'}}}
    app=create_app(config);password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        uid=db.execute('INSERT INTO users(username,name,password) VALUES(?,?,?)',('reader','Reader',generate_password_hash(password))).lastrowid;db.execute('INSERT INTO access VALUES(?,?)',(uid,'test'))
    server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox']);context=browser.new_context(viewport={'width':1600,'height':1100},permissions=['clipboard-read','clipboard-write']);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url);page.locator('#username').fill('reader');page.locator('#password').fill(password);page.locator('#login-submit').click();expect(page.locator('#storage-summary')).to_contain_text('used');page.locator('.file-row').filter(has_text='plan.md').click(button='right');expect(page.get_by_role('menuitem',name='Edit document')).to_be_visible();expect(page.get_by_role('menuitem',name='Rename…')).to_have_count(0);expect(page.get_by_role('menuitem',name='Move to Trash')).to_have_count(0);page.get_by_role('menuitem',name='Open',exact=True).click()
            page.locator('#comment-body').fill('Clarify this saved plan.');page.locator('#post-button').click();expect(page.locator('.thread')).to_have_count(1)
            page.locator('#edit-file').click();expect(page.locator('.tiptap')).to_be_visible();expect(page.locator('.tiptap table')).to_be_visible()
            # No-op editing preserves source byte for byte.
            page.locator('#save-document').click();assert (root/'plan.md').read_text()==source
            page.locator('.tiptap h1').click();page.keyboard.press('End');page.keyboard.type(' revised')
            page.locator('#save-document').click();expect(page.locator('#document-save-state')).to_have_text('All changes saved');assert (root/'plan.md').read_text().startswith('# Building plan revised')
            assert 'print("safe")' in (root/'plan.md').read_text();assert re.search(r'\|\s*Test\s*\|\s*Open\s*\|', (root/'plan.md').read_text()), (root/'plan.md').read_text()
            expect(page.locator('.thread')).to_contain_text('Clarify this saved plan.');expect(page.locator('.stale')).to_be_visible()
            # Highlight new text while editing and comment on the saved revision.
            page.locator('.tiptap h1').click();page.keyboard.press('Home');page.keyboard.down('Shift');page.keyboard.press('End');page.keyboard.up('Shift');expect(page.locator('#selection-comment')).to_be_visible();page.locator('#selection-comment').click();page.locator('#comment-body').fill('Title reviewed.');page.locator('#post-button').click();expect(page.locator('.thread')).to_have_count(2)
            page.locator('#comment-body').fill('Unposted draft');page.locator('#copy-agent-prompt').click();expect(page.locator('#toast')).to_contain_text('Post your draft');page.locator('#comment-body').fill('');page.locator('#copy-agent-prompt').click();expect(page.locator('#export-state')).to_contain_text('Saved to project');assert 'direct human edits' in page.evaluate('navigator.clipboard.readText()');assert (root/'.reviews/plan.md.review.md').exists()
            page.screenshot(path='/tmp/margin-editor-desktop.png')
            # Preserve concurrent changes and the unsaved draft.
            page.locator('.tiptap h1').click();page.keyboard.press('End');page.keyboard.type(' draft');(root/'plan.md').write_text('# External revision')
            page.locator('#save-document').click();expect(page.locator('#document-save-state')).to_contain_text('changed');expect(page.locator('.tiptap h1')).to_contain_text('draft');assert (root/'plan.md').read_text()=='# External revision'
            page.on('dialog',lambda d:d.accept());page.locator('#reload-document').click();expect(page.locator('#document h1')).to_have_text('External revision')
            page.locator('#version-history').click();expect(page.locator('.history-row')).to_have_count(1);page.locator('.history-row').click();expect(page.locator('#document-source')).to_have_value(source);page.locator('#finish-editing').click();expect(page.locator('#document h1')).to_have_text('Building plan')
            page.locator('#back-button').click();page.locator('.file-row').filter(has_text='plain.txt').click();page.locator('#edit-file').click();expect(page.locator('#document-source')).to_have_value('<b>Plain text</b>\n\n  spaces\n');page.locator('#document-source').fill('<b>Plain text</b>\n\n  spaces revised\n');page.locator('#finish-editing').click();expect(page.locator('#document-source')).to_have_count(0);assert (root/'workspace/plain.txt').read_text()=='<b>Plain text</b>\n\n  spaces revised\n';assert page.locator('#document b').count()==0
            page.locator('#back-button').click();page.locator('.file-row').filter(has_text='advanced.md').click();page.locator('#edit-file').click();expect(page.locator('#document-source')).to_be_visible();expect(page.locator('#editor-notice')).to_contain_text('preserves');expect(page.get_by_role('button',name='Bold',exact=True)).to_be_visible();page.locator('#document-source').evaluate('(area)=>{area.focus();const at=area.value.indexOf("Heading");area.setSelectionRange(at,at+7)}');page.get_by_role('button',name='Bold',exact=True).click();assert '**Heading**' in page.locator('#document-source').input_value();page.get_by_role('button',name='Underline',exact=True).click();assert '<u>Heading</u>' in page.locator('#document-source').input_value();page.get_by_role('button',name='Undo',exact=True).click();assert '<u>' not in page.locator('#document-source').input_value();page.get_by_role('button',name='Redo',exact=True).click();assert '<u>' in page.locator('#document-source').input_value();page.locator('#finish-editing').click();expect(page.locator('#document-source')).to_have_count(0);assert (root/'workspace/advanced.md').read_text().startswith('---\ntitle: Metadata\n---');assert '[^1]: Footnote' in (root/'workspace/advanced.md').read_text()
            page.locator('#back-button').click();page.locator('.file-row').filter(has_text='notes.md').click();page.locator('#comment-body').fill('Keep this comment.');page.locator('#post-button').click();expect(page.locator('.thread')).to_have_count(1)
            page.locator('#back-button').click();page.locator('.file-row').filter(has_text='notes.md').click(button='right');page.get_by_role('menuitem',name='Rename…').click();page.locator('[name=name]').fill('renamed.md');page.locator('#workspace-form button').click();expect(page.locator('#document-name')).to_have_text('renamed.md');expect(page.locator('.thread')).to_contain_text('Keep this comment.')
            page.locator('#back-button').click();page.locator('.file-row').filter(has_text='renamed.md').click(button='right');page.get_by_role('menuitem',name='Edit document').click();expect(page.locator('.tiptap')).to_be_visible();page.locator('#finish-editing').click();expect(page.locator('.tiptap')).to_have_count(0);page.locator('#back-button').click();page.locator('.file-row').filter(has_text='renamed.md').click(button='right');page.get_by_role('menuitem',name='Move to Trash').click();expect(page.locator('#library')).to_be_visible();assert not (root/'workspace/renamed.md').exists();page.locator('#view-trash').click();expect(page.locator('.trash-row')).to_contain_text('renamed.md');expect(page.locator('#storage-detail')).to_contain_text('in Trash');page.locator('.trash-row button').click();expect(page.locator('.trash-row')).to_have_count(0);page.locator('#close-modal').click();page.locator('.file-row').filter(has_text='renamed.md').click();expect(page.locator('.thread')).to_contain_text('Keep this comment.')
            page.locator('#edit-file').click();page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/margin-editor-mobile.png');assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors;browser.close();print('PASS: source formatting toolbar, storage/Trash usage, file context menus, rich Markdown and source editing, plain text fidelity, original source edits, comments, handoff, history, conflicts, rename/trash/restore and mobile layout.')
    finally:server.shutdown();thread.join();broker.shutdown();bt.join();broker.server_close()
