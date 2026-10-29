"""Local preview only: exercises the interface with disposable accounts."""
import json
import os
import secrets
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
password=secrets.token_urlsafe(24)
with sqlite3.connect('/tmp/margin-preview/db.sqlite') as db:
    db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,1) ON CONFLICT(username) DO UPDATE SET password=excluded.password',('preview','Administrator',generate_password_hash(password)))
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('MARGIN_CHROMIUM'),headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765/')
    page.screenshot(path='/tmp/margin-login.png')
    page.locator('#username').fill('preview');page.locator('#password').fill(password)
    page.locator('#login-submit').click()
    page.locator('.file-row').first.wait_for()
    page.screenshot(path='/tmp/margin-library.png')
    page.locator('.file-row').filter(has_text='01-ai-agent-pipeline-plan').click()
    page.locator('#document h1').wait_for()
    page.evaluate("""() => {const n=document.querySelector('#document h1');const r=document.createRange();r.selectNodeContents(n);const s=getSelection();s.removeAllRanges();s.addRange(r);n.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));}""")
    page.locator('#comment-body').fill('Please make the implementation sequence clearer.')
    page.locator('#post-button').click()
    page.locator('.thread-body').filter(has_text='implementation sequence').first.wait_for()
    page.locator('.thread-actions button').filter(has_text='Reply').first.click()
    page.locator('#comment-body').fill('Start with the contracts and a working vertical slice.')
    page.locator('#post-button').click()
    page.locator('.reply').first.wait_for()
    page.locator('#export-button').click()
    expect(page.locator("#export-state")).to_contain_text("Saved to project")
    assert Path('/tmp/margin-preview/project/.reviews/plans/01-ai-agent-pipeline-plan.md.review.md').exists()
    page.screenshot(path='/tmp/margin-reader.png')
    page.locator('.thread-actions button').filter(has_text='Resolve').first.click()
    page.locator('#filter-all').click()
    page.locator('.thread.resolved').first.wait_for()
    page.locator('#team-button').click()
    page.locator('#invite-form input[name="name"]').fill('Test Colleague')
    username='reviewer-'+secrets.token_hex(4)
    page.locator('#invite-form input[name="username"]').fill(username)
    page.locator('#invite-form button').click()
    page.locator('#invite-result input').wait_for()
    link=page.locator('#invite-result input').input_value()
    other=browser.new_context(); colleague=other.new_page()
    colleague.goto(link);colleague.locator('#password').fill(secrets.token_urlsafe(24));colleague.locator('#login-submit').click()
    colleague.locator('.file-row').first.wait_for()
    assert not colleague.locator('#team-button').is_visible()
    page.locator('#close-modal').click()
    page.locator('#back-button').click()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path='/tmp/margin-mobile-library.png')
    page.locator('.file-row').first.click()
    page.locator('#document h1').wait_for()
    page.screenshot(path='/tmp/margin-mobile-reader.png')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors,errors
    print(json.dumps({'browser_errors':errors,'checks':['login','library','passage selection','comment','reply','export','resolve','invitation','colleague activation','mobile layout'],'screenshots':'/tmp/margin-*.png'}))
    browser.close()
