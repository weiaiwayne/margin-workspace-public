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
    connected=Path(tmp)/'connected';connected.mkdir();(connected/'Existing folder').mkdir();(connected/'Existing folder'/'plan.md').write_text('# Existing plan');config['projects']['connected']={'root':str(connected),'name':'Connected project','writable_directory':'.'}
    app=create_app(config);password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        uid=db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,1)',('reader','Reader',generate_password_hash(password))).lastrowid;db.execute('INSERT INTO access VALUES(?,?)',(uid,'test'))
    server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox'])
            page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            phase={'created':False,'catalog':0,'files':0}
            projects=[{'id':'test','name':'Initial project','pending':False}, {'id':'connected','name':'Connected project','pending':False,'server_path':'/synthetic/existing-folder','private':True}]
            def catalog(route):
                if not phase['created']:
                    route.fulfill(json={'projects':projects[:1],'can_manage_workspaces':True});return
                phase['catalog']+=1
                if phase['catalog']==1:
                    route.fulfill(status=502,body='Service restarting');return
                route.fulfill(json={'projects':[projects[0],{**projects[1],'pending':phase['catalog']==2}],'can_manage_workspaces':True})
            def create(route):
                phase['created']=True
                route.fulfill(json={**projects[1],'pending':True})
            def files(route):
                phase['files']+=1
                if phase['files']==1:route.fulfill(status=503,json={'error':'Still starting'})
                else:route.continue_()
            page.route('**/api/projects',catalog);page.route('**/api/workspaces',create)
            page.route('**/api/files?project=connected',files)
            page.goto(f'http://127.0.0.1:{server.server_port}/');page.locator('#username').fill('reader');page.locator('#password').fill(password);page.locator('#login-submit').click()
            expect(page.locator('#workspace-status')).to_contain_text('Folder connected')
            page.locator('#search').fill('does not match')
            page.locator('#manage-workspaces').click();page.locator('#workspace-name').fill('Connected project');page.locator('#workspace-path').fill('/synthetic/existing-folder');page.locator('#create-workspace-submit').click()
            expect(page.locator('#workspace-status')).to_contain_text('Connecting')
            expect(page.locator('#workspace-status')).to_have_text('Folder connected · /synthetic/existing-folder',timeout=20000)
            expect(page.locator('#library')).to_be_visible();expect(page.locator('#search')).to_have_value('')
            expect(page.locator('#folders [data-folder-path="Existing folder"]')).to_be_visible()
            expect(page.locator('.file-row').filter(has_text='plan.md')).to_be_visible()
            expect(page.locator('#toast')).to_have_text('Private workspace connected.')
            assert phase['catalog']>=4 and phase['files']>=2 and not errors,(phase,errors)
            page.locator('#project-select').select_option('test')
            expect(page.locator('#project-name')).to_have_text('Initial project')
            expect(page.locator('#folders [data-folder-path="Existing folder"]')).to_have_count(0)
            expect(page.locator('#workspace-status')).to_have_text('Folder connected · Initial project')
            browser.close();print('PASS: connection survives catalog restart, pending activation and first-file 503; folders and persistent confirmation appear without refresh; switching clears stale navigation.')
    finally:server.shutdown();thread.join()
