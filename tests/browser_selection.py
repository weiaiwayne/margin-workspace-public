import re
"""Disposable browser regression for passage commenting and navigation."""
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

with tempfile.TemporaryDirectory(prefix='margin-selection-') as tmp:
    root=Path(tmp)/'project'; root.mkdir()
    (root/'original.md').write_text('# Original\n\nKeep this **review** draft.\n\n' + ('Filler paragraph.\n\n' * 60) + 'Target passage below.\n')
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
            page.locator('.file-row').click()
            expect(page.locator('#agent-prompt')).to_have_value(re.compile(r'Work in the project folder.*original\.md.*\.reviews/original\.md\.review\.md.*preserve those edits', re.S))
            assert page.locator('.document-scroll > .agent-handoff').count()==1
            assert page.locator('.document-end + .agent-handoff').count()==1
            page.locator('#agent-prompt').scroll_into_view_if_needed()
            expect(page.locator('#agent-prompt')).to_be_in_viewport()
            expect(page.locator('#copy-agent-prompt')).to_be_visible()
            page.locator('#comments-toggle').click()
            expect(page.locator('#agent-prompt')).to_be_in_viewport()
            page.locator('#comments-toggle').click()
            page.locator('#document h1').scroll_into_view_if_needed()
            def select(selector):
                page.locator(selector).evaluate("""element=>{
                  const range=document.createRange();range.selectNodeContents(element);
                  const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
                }""")
            select('#document p:first-of-type')
            expect(page.locator('#selection-comment')).to_be_visible()
            expect(page.locator('#quote-preview')).to_be_hidden()
            page.locator('#selection-comment').click()
            expect(page.locator('#quote-text')).to_have_text('Keep this review draft.')
            expect(page.locator('#comment-body')).to_be_focused()
            page.locator('#comment-body').fill('Clarify this passage.')
            page.locator('#post-button').click()
            expect(page.locator('.thread')).to_have_count(1)
            page.reload()
            page.locator('.thread').click()
            expect(page.locator('.comment-highlight')).to_have_count(3)
            assert page.locator('.comment-highlight').all_text_contents()==['Keep this ', 'review', ' draft.']
            # Right-click selected text opens the same action at the pointer.
            page.locator('#document p:last-of-type').scroll_into_view_if_needed()
            select('#document p:last-of-type')
            rect=page.evaluate('window.getSelection().getRangeAt(0).getBoundingClientRect().toJSON()')
            page.mouse.click(rect['x']+10,rect['y']+5,button='right')
            expect(page.locator('#selection-comment')).to_be_visible()
            page.locator('#selection-comment').click()
            expect(page.locator('#quote-text')).to_have_text('Target passage below.')
            page.locator('#comment-body').fill('Review the final passage.')
            page.locator('#post-button').click()
            expect(page.locator('.thread')).to_have_count(2)
            page.locator('#document h1').scroll_into_view_if_needed()
            page.locator('.thread').last.click()
            expect(page.locator('.comment-highlight')).to_have_text('Target passage below.')
            expect(page.locator('.comment-highlight')).to_be_in_viewport()
            # Keyboard activation follows the passage too.
            page.locator('.thread').first.focus();page.keyboard.press('Enter')
            expect(page.locator('.comment-highlight')).to_have_count(3)
            # Dismissing selection leaves the existing draft untouched.
            page.locator('#comment-body').fill('Keep my draft')
            select('#document p:first-of-type')
            expect(page.locator('#selection-comment')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.locator('#selection-comment')).to_be_hidden()
            expect(page.locator('#comment-body')).to_have_value('Keep my draft')
            page.locator('#comment-body').fill('')
            # Mobile action fits the viewport and opens the composer.
            page.set_viewport_size({'width':390,'height':844})
            page.locator('#comments-toggle').click()
            select('#document p:first-of-type')
            expect(page.locator('#selection-comment')).to_be_visible()
            box=page.locator('#selection-comment').bounding_box()
            assert box['x']>=0 and box['x']+box['width']<=390
            page.locator('#selection-comment').click()
            expect(page.locator('#comment-body')).to_be_focused()
            page.locator('.thread').first.click()
            expect(page.locator('#comments-panel')).to_be_hidden()
            expect(page.locator('.comment-highlight').first).to_be_in_viewport()
            # Ambiguous and removed passages must never jump to an arbitrary match.
            page.evaluate("revealPassage({quote:'Filler paragraph.',section:''})")
            expect(page.locator('#toast')).to_contain_text('more than once')
            page.evaluate("revealPassage({quote:'Deleted passage.',section:''})")
            expect(page.locator('#toast')).to_contain_text('could not be located')
            assert not errors,errors
            browser.close()
            print('PASS: selection action, context menu, quoted comments, cross-format highlights, scroll, keyboard, mobile, drafts, and missing/ambiguous passages.')
    finally:
        server.shutdown();thread.join()
