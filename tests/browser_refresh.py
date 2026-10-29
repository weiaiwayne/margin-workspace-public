"""Regression: discover new disk files on reload, tab restore, and while reviewing.
Run: MARGIN_CHROMIUM=/path/to/chromium .venv/bin/python tests/browser_refresh.py
Uses only disposable local files/accounts; never accesses the production database.
"""
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

with tempfile.TemporaryDirectory(prefix='margin-refresh-') as tmp:
    root=Path(tmp)/'project'; root.mkdir()
    (root/'original.md').write_text('# Original\n\nKeep this review draft.\n')
    config={'testing':True,'secure_cookie':False,'base_path':'/','database':str(Path(tmp)/'db.sqlite'),
            'projects':{'test':{'root':str(root),'name':'Test project'}}}
    app=create_app(config)
    password=secrets.token_urlsafe(24)
    with sqlite3.connect(config['database']) as db:
        db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,1)',('reviewer','Reviewer',generate_password_hash(password)))
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),args=['--no-sandbox'])
            page=browser.new_page(); errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.locator('#username').fill('reviewer');page.locator('#password').fill(password)
            page.locator('#login-submit').click();expect(page.locator('.file-row')).to_have_count(1)
            (root/'after-reload.md').write_text('# Added before browser reload')
            page.reload();expect(page.locator('.file-row')).to_have_count(2)
            (root/'after-pageshow.md').write_text('# Added before tab restore')
            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
            expect(page.locator('.file-row')).to_have_count(3)
            page.locator('.file-row').filter(has_text='original').click()
            page.locator('#comment-body').fill('My unsent review must survive refresh.')
            (root/'while-reading.md').write_text('# Added while reading')
            expect(page.locator('#file-count')).to_have_text('4',timeout=15000)
            expect(page.locator('#comment-body')).to_have_value('My unsent review must survive refresh.')
            expect(page.locator('#document h1')).to_have_text('Original')
            page.locator('#back-button').click();expect(page.locator('.file-row')).to_have_count(4)
            # Deletion and folder additions are refreshed too, without the refresh button.
            (root/'after-reload.md').unlink();(root/'new-folder').mkdir()
            (root/'new-folder'/'fresh.md').write_text('# Fresh folder')
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.locator('#folders')).to_contain_text('new-folder')
            expect(page.locator('.file-row').filter(has_text='after-reload')).to_have_count(0)
            assert not errors,errors
            page.locator('.file-row').filter(has_text='original').click()
            expect(page.locator('#comment-body')).to_have_value('My unsent review must survive refresh.')
            page.locator('#comment-body').fill('')
            browser.close()
            print('PASS: browser reload, restored tab, automatic discovery, additions/deletions, and draft preservation.')
    finally:
        server.shutdown();thread.join()
