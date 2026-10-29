"""Administrator workspace UI against a disposable Unix provisioning broker."""
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from workspace_broker import Handler,Server
from playwright.sync_api import sync_playwright,expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

with tempfile.TemporaryDirectory(prefix='margin-server-workspaces-') as tmp:
    base=Path(tmp);example_project=base/'example_project';example_project.mkdir();(example_project/'plan.md').write_text('# Example plan')
    existing=base/'existing';existing.mkdir();(existing/'existing.md').write_text('# Existing document')
    registry=base/'registry.json';registry.write_text('{}')
    class FakeBroker:
        config={'lock':str(base/'broker.lock')}
        def browse(self,path):return {'path':str(base),'parent':None,'folders':[{'name':'Existing project','path':str(existing)}]}
        def provision(self,body):
            root=existing if body['mode']=='existing' else base/'new'
            root.mkdir(exist_ok=True);(root/'.reviews').mkdir(exist_ok=True)
            if body['mode']=='existing':(root/'workspace').mkdir(exist_ok=True)
            pid='ws-'+secrets.token_hex(4);data=json.loads(registry.read_text())
            data[pid]={'name':body['name'],'root':str(root),'server_path':str(root),'reviews':str(root/'.reviews'),'writable_directory':'.' if body['mode']=='new' else 'workspace','private':True,'owner_id':body['owner_id'],'pending':False}
            registry.write_text(json.dumps(data));return {'id':pid,'server_path':str(root),'pending':False}
    broker=Server(str(base/'broker.sock'),Handler);broker.broker=FakeBroker();bt=threading.Thread(target=broker.serve_forever,daemon=True);bt.start()
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(base/'db.sqlite'),'workspace_registry':str(registry),'workspace_broker_socket':str(base/'broker.sock'),'projects':{'example-project':{'root':str(example_project),'name':'Example project'}}}
    app=create_app(config);password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        for name,admin in [('admin',1),('reviewer.one',0),('reviewer.two',0)]:
            uid=db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,?)',(name,name,generate_password_hash(password),admin)).lastrowid
            if not admin:db.execute('INSERT INTO access VALUES(?,?)',(uid,'example-project'))
    server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def login(page,user):
                page.goto(url);page.locator('#username').fill(user);page.locator('#password').fill(password);page.locator('#login-submit').click();expect(page.locator('#workspace')).to_be_visible()
            login(page,'admin');page.locator('#manage-workspaces').click();page.locator('#workspace-name').fill('Private files');page.locator('#workspace-mode').select_option('new');page.locator('#create-workspace-submit').click();expect(page.locator('#project-name')).to_have_text('Private files')
            page.locator('#new-md').click();page.locator('#document-title').fill('owner.md');page.locator('#document-title').press('Enter');expect(page.locator('#document-title')).to_be_enabled();page.locator('#source-mode').click();page.locator('#document-source').fill('# Owner only');page.locator('#finish-editing').click();expect(page.locator('#document h1')).to_have_text('Owner only')
            assert (base/'new/owner.md').exists()
            page.locator('#back-button').click();page.locator('#new-folder').click();page.locator('[name=name]').fill('Notes');page.locator('#workspace-form button').click();expect(page.locator('#library-title')).to_have_text('Notes')
            page.locator('#folders [data-folder-path=\"Notes\"]').click(button='right');page.get_by_role('menuitem',name='Rename…').click();page.locator('[name=name]').fill('Renamed');page.locator('#workspace-form button').click();expect(page.locator('#library-title')).to_have_text('Renamed')
            page.locator('#manage-workspaces').click();page.locator('#workspace-name').fill('Connected project');page.locator('#browse-server').click();expect(page.locator('.server-folder')).to_contain_text('Existing project');page.locator('#workspace-path').fill(str(existing));page.locator('#create-workspace-submit').click();expect(page.locator('#project-name')).to_have_text('Connected project')
            page.locator('.file-row').click();expect(page.locator('#document h1')).to_have_text('Existing document');expect(page.locator('#edit-file')).to_be_hidden()
            page.locator('#back-button').click();page.locator('#manage-workspaces').click();page.screenshot(path='/tmp/margin-server-workspaces.png');page.locator('#close-modal').click()
            page.locator('#team-button').click();expect(page.locator('input[name=project]')).to_have_count(1);expect(page.locator('input[name=project]')).to_have_value('example-project');page.locator('#close-modal').click()
            for user in ['reviewer.one','reviewer.two']:
                other=browser.new_context();collaborator=other.new_page();login(collaborator,user)
                expect(collaborator.locator('#manage-workspaces')).to_be_hidden();expect(collaborator.locator('#project-select option')).to_have_count(1)
                expect(collaborator.locator('#project-select')).to_have_value('example-project')
                assert other.request.get(url+'api/server-folders').status==403
                for pid in json.loads(registry.read_text()):assert other.request.get(url+'api/files?project='+pid).status==403
                other.close()
            assert not errors,errors
            browser.close();print('PASS: admin folder browsing, new/existing workspaces, root file creation, folder rename, private grant filtering, and both collaborator restrictions.')
    finally:server.shutdown();thread.join();broker.shutdown();bt.join();broker.server_close()
