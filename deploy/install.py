#!/usr/bin/env python3
"""Fresh Ubuntu/Debian VPS install. --plan performs no writes or commands."""
import argparse,json,os,pwd,re,shutil,subprocess
from pathlib import Path

APP=Path('/opt/margin-workspace')
CONF=Path('/etc/margin')
MARKER='# Managed by Margin Workspace installer\n'

def run(*args):subprocess.run([str(a) for a in args],check=True)

def configuration(domain, allowed):
    shared={'name':'Shared workspace','root':'/srv/margin/projects/shared','server_path':'/srv/margin-projects/shared',
            'reviews':'/srv/margin/projects/shared/.reviews','writable_directory':'.','storage_limit_bytes':1073741824}
    config={'database':'/var/lib/margin/margin.sqlite','public_url':f'https://{domain}/','base_path':'/',
            'secure_cookie':True,'proxy':True,'hosts':[domain,'localhost','127.0.0.1'],'projects':{'shared':shared},
            'edit_project_documents':True,'workspace_registry':str(CONF/'workspaces.json'),
            'workspace_broker_socket':'/run/margin-broker/control.sock'}
    broker={'socket':config['workspace_broker_socket'],'registry':config['workspace_registry'],
            'lock':str(CONF/'workspaces.lock'),'allowed_roots':allowed,
            'protected_paths':[str(APP),'/srv/margin','/var/www/margin-acme'],
            'existing_sources':['/srv/margin-projects/shared'],'document_sources':{'shared':'/srv/margin-projects/shared'},
            'document_history':'/var/lib/margin/source-history','new_folder_parent':'/srv/margin-projects',
            'mount_root':'/srv/margin/projects','dropin':'/etc/systemd/system/margin.service.d/workspaces.conf'}
    return config,broker

def nginx(domain,tls=False):
    challenge='location /.well-known/acme-challenge/ { root /var/www/margin-acme; }'
    text=MARKER+f'server {{\n listen 80;\n server_name {domain};\n {challenge}\n'
    text+=(' location / { return 301 https://$host$request_uri; }\n}\n' if tls else ' location / { return 503; }\n}\n')
    if tls:
        text+=f'''server {{
 listen 443 ssl;
 server_name {domain};
 ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
 ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
 ssl_protocols TLSv1.2 TLSv1.3;
 location / {{
  proxy_pass http://127.0.0.1:8766;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header X-Forwarded-Proto $scheme;
  client_max_body_size 0;
  proxy_request_buffering off;
  proxy_http_version 1.1;
  proxy_send_timeout 300s;
  proxy_read_timeout 3600s;
  access_log off;
 }}
}}
'''
    return text

def arguments():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--domain',required=True);p.add_argument('--email',required=True)
    p.add_argument('--username',default='admin');p.add_argument('--name',default='Administrator')
    p.add_argument('--allow-root',action='append',default=[]);p.add_argument('--plan',action='store_true')
    a=p.parse_args()
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',a.domain):p.error('Use a lowercase DNS hostname, such as margin.example.com.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',a.email) or a.email.startswith('-'):p.error('Provide a valid certificate contact email.')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,64}',a.username) or a.username.startswith('-'):p.error('Use a 3–64 character administrator username.')
    allowed=['/srv/margin-projects']
    for value in a.allow_root:
        path=Path(value)
        if not path.is_absolute() or '..' in path.parts or not re.fullmatch(r'/[A-Za-z0-9_/-]+',value):p.error('Allowed roots must be simple absolute directory paths.')
        resolved=path.resolve()
        if resolved in [Path(x) for x in ('/','/etc','/proc','/sys','/dev','/var','/var/lib')]:p.error('Choose a project parent, not a sensitive system directory.')
        allowed.append(str(resolved))
    a.allowed=list(dict.fromkeys(allowed));return a

def main():
    a=arguments();config,broker=configuration(a.domain,a.allowed)
    if a.plan:
        print(json.dumps({'install_path':str(APP),'url':config['public_url'],'allowed_roots':a.allowed,
                          'shared_folder':'/srv/margin-projects/shared','admin':a.username,
                          'steps':['Install OS/Python dependencies','Create margin service user','Obtain TLS certificate with webroot',
                                   'Install isolated web service and local folder broker','Create one-time administrator setup link']},indent=2));return
    if os.geteuid()!=0:raise SystemExit('Run with sudo; use --plan to preview without changes.')
    if (CONF/'config.json').exists():raise SystemExit('An installation already exists. Follow docs/OPERATIONS.md; no configuration was overwritten.')
    if any(Path('/etc/systemd/system', name).exists() for name in ('margin.service','margin-broker.service')):raise SystemExit('Existing Margin service units found. Preserve them and follow the update/recovery guide.')
    if not Path('/run/systemd/system').exists() or not shutil.which('apt-get'):raise SystemExit('This installer needs a systemd-based Ubuntu/Debian VPS.')
    site=Path('/etc/nginx/sites-available')/('margin-'+a.domain)
    enabled=Path('/etc/nginx/sites-enabled')/site.name
    if site.exists() and not site.read_text().startswith(MARKER):raise SystemExit('An unrelated nginx configuration uses this filename; refusing to replace it.')
    if Path('/srv/margin-projects/shared').exists():raise SystemExit('The default shared folder exists. Preserve it and follow the manual recovery guide.')
    source=Path(__file__).resolve().parents[1]
    if source!=APP and APP.exists():raise SystemExit('Install path already exists. Clone into /opt/margin-workspace or use a fresh path.')
    for root in a.allowed:
        if root!='/srv/margin-projects' and not Path(root).is_dir():raise SystemExit('Allowed project parent does not exist: '+root)
    # Existing nginx must not already serve the requested hostname on another site.
    for file in Path('/etc/nginx/sites-enabled').glob('*'):
        if file.resolve()!=site.resolve() and file.is_file() and re.search(r'\bserver_name\s+[^;]*\b'+re.escape(a.domain)+r'\s*[; ]',file.read_text()):
            raise SystemExit('This hostname already has an nginx site. Ask your agent to integrate using docs/VPS.md.')
    os.umask(0o022)
    run('apt-get','update')
    run('apt-get','install','-y','python3','python3-venv','python3-pip','nginx','certbot','acl','fonts-dejavu-core','fonts-noto-cjk','libpango-1.0-0','libpangoft2-1.0-0','libharfbuzz-subset0')
    if source!=APP:
        shutil.copytree(source,APP,ignore=shutil.ignore_patterns('.git','.venv','node_modules','__pycache__','.pytest_cache','config.json','.env','*.sqlite*'))
    run('python3','-m','venv',APP/'.venv');run(APP/'.venv/bin/pip','install','-r',APP/'requirements.txt')
    run('chown','-R','root:root',APP)
    APP.chmod(0o755)
    try:account=pwd.getpwnam('margin')
    except KeyError:
        run('useradd','--system','--home-dir','/var/lib/margin','--shell','/usr/sbin/nologin','margin');account=pwd.getpwnam('margin')
    Path('/var/www/margin-acme').mkdir(parents=True,exist_ok=True)
    site.write_text(nginx(a.domain));enabled.symlink_to(site) if not enabled.exists() else None
    run('nginx','-t');run('systemctl','enable','--now','nginx');run('systemctl','reload','nginx')
    # No login page is exposed until HTTPS succeeds. Certbot failure can be retried here.
    run('certbot','certonly','--webroot','-w','/var/www/margin-acme','--cert-name',a.domain,'-d',a.domain,
        '--email',a.email,'--agree-tos','--non-interactive','--keep-until-expiring')
    for directory in (CONF,Path('/var/lib/margin'),Path('/srv/margin-projects/shared'),Path('/srv/margin/projects/shared'),Path('/etc/systemd/system/margin.service.d')):
        directory.mkdir(parents=True,exist_ok=True)
    for directory in (Path('/var/lib/margin'),Path('/srv/margin-projects/shared')):
        os.chown(directory,account.pw_uid,account.pw_gid);directory.chmod(0o700)
    CONF.chmod(0o750);os.chown(CONF,0,account.pw_gid)
    for name,value,mode in [('config.json',config,0o640),('broker.json',broker,0o600),('workspaces.json',{},0o640)]:
        target=CONF/name;target.write_text(json.dumps(value,indent=2)+'\n');os.chown(target,0,account.pw_gid);target.chmod(mode)
    for name in ('margin.service','margin-broker.service'):
        shutil.copy2(APP/'deploy'/name,Path('/etc/systemd/system')/name)
    run('runuser','-u','margin','--',APP/'.venv/bin/python',APP/'app.py','--config',CONF/'config.json','--username',a.username,'--name',a.name)
    run('systemctl','daemon-reload');run('systemctl','enable','--now','margin-broker.service','margin.service')
    site.write_text(nginx(a.domain,True));run('nginx','-t');run('systemctl','reload','nginx')
    hook=Path('/etc/letsencrypt/renewal-hooks/deploy/margin-nginx');hook.parent.mkdir(parents=True,exist_ok=True)
    hook.write_text('#!/bin/sh\n/usr/sbin/nginx -t && /usr/bin/systemctl reload nginx\n');hook.chmod(0o755)
    run('systemctl','enable','--now','certbot.timer')
    print('Ready at '+config['public_url']+' — open the private setup link printed above to choose your password.')

if __name__=='__main__':main()
