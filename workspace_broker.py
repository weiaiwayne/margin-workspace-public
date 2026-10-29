"""Root-only local folder provisioning broker; never exposed over TCP.
The web app checks administrator authentication; the Unix socket accepts only
root/the margin group. Selected folders are mounted into the unprivileged app.
"""
from __future__ import annotations
import argparse
import workspace_access
import hashlib
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import socketserver
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler

EXCLUDED={'.git','.reviews','node_modules','external','venv','__pycache__','vendor','dist','build'}
class ProvisionError(Exception):pass

class Broker:
    def __init__(self, config):
        self.config=config
        self.registry=Path(config['registry'])
        self.allowed=[Path(p).resolve() for p in config['allowed_roots']]
        self.protected=[Path(p).resolve() for p in config['protected_paths']]

    def read_registry(self):
        return json.loads(self.registry.read_text()) if self.registry.exists() else {}

    def write_registry(self, value):
        fd,temp=tempfile.mkstemp(dir=self.registry.parent,prefix='.workspaces-')
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
            user=pwd.getpwnam('margin');os.chown(temp,0,user.pw_gid);os.chmod(temp,0o640)
            os.replace(temp,self.registry)
        finally:
            if os.path.exists(temp):os.unlink(temp)

    def path(self, value, *, attaching=False):
        if not isinstance(value,str) or not value.startswith('/') or len(value)>1000 or any(ord(c)<32 or c in '\\:%' for c in value):
            raise ProvisionError('Use an absolute server folder path without control characters, backslashes, colons or percent signs.')
        if any(p in ('.','..') or p.startswith('.') for p in value.split('/') if p):
            raise ProvisionError('Hidden folders and parent traversal are not allowed.')
        path=Path(value)
        for parent in [path,*path.parents]:
            if parent.is_symlink():raise ProvisionError('Linked folders cannot be connected.')
        path=path.resolve()
        if not any(path.is_relative_to(base) for base in self.allowed):
            raise ProvisionError('Choose a project under one of the available server locations.')
        if any(path==blocked or path.is_relative_to(blocked) for blocked in self.protected):
            raise ProvisionError('Margin and system service folders cannot be connected.')
        if attaching:
            if path in self.allowed or any(blocked.is_relative_to(path) for blocked in self.protected):
                raise ProvisionError('Choose a specific project folder, not a system or service parent folder.')
            registered=[Path(p).resolve() for p in self.config.get('existing_sources',[])]
            registered += [Path(p['server_path']) for p in self.read_registry().values()]
            if any(path==p or path.is_relative_to(p) or p.is_relative_to(path) for p in registered):
                raise ProvisionError('This folder overlaps an existing workspace. Choose a separate project folder.')
        return path

    def browse(self, value):
        if not value or value=='/':
            return {'path':'/','parent':None,'folders':[{'name':str(p),'path':str(p)} for p in self.allowed if p.is_dir()]}
        path=self.path(value)
        if not path.is_dir():raise ProvisionError('Folder not found.')
        folders=[]
        for entry in sorted(path.iterdir(),key=lambda p:p.name.lower()):
            if entry.name.startswith('.') or entry.name in EXCLUDED or entry.is_symlink() or not entry.is_dir():continue
            if any(entry==p or entry.is_relative_to(p) for p in self.protected):continue
            folders.append({'name':entry.name,'path':str(entry)})
            if len(folders)>=1000:break
        return {'path':str(path),'parent':'/' if path in self.allowed else str(path.parent),'folders':folders}

    def grant(self, root, writable=False):
        # Batch ACLs; do not change source owners or recursively follow symlinks.
        directories, documents = [], []
        count=0
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if not d.startswith('.') and d not in EXCLUDED and not (Path(directory)/d).is_symlink()]
            directories.append(directory)
            count += len(files) + 1
            if count>100000:raise ProvisionError('Folder is too large to provision; choose a smaller project.')
            for name in files:
                path=Path(directory)/name
                if path.is_symlink() or name.startswith('.'):continue
                if writable or path.suffix.lower() in ('.md','.txt','.pdf'):
                    documents.append(str(path))
        for entries,permission in [(directories,'u:margin:rwx' if writable else 'u:margin:r-x'),(documents,'u:margin:rw-' if writable else 'u:margin:r--')]:
            for offset in range(0,len(entries),128):
                subprocess.run(['setfacl','-m',permission,'--',*entries[offset:offset+128]],check=True)

    def provision(self, body):
        name=body.get('name','').strip();mode=body.get('mode');owner=body.get('owner_id')
        if not name or len(name)>100 or mode not in ('existing','new') or type(owner) is not int or owner<1:
            raise ProvisionError('Provide a workspace name, folder choice, and administrator owner.')
        supplied=body.get('path','').strip()
        if not supplied and mode=='new':
            slug=re.sub('[^a-z0-9-]+','-',name.lower()).strip('-')[:60] or 'project'
            supplied=str(Path(self.config['new_folder_parent'])/slug)
        path=self.path(supplied,attaching=True)
        if mode=='existing' and not path.is_dir():raise ProvisionError('The selected folder does not exist.')
        if mode=='new' and (path.exists() or not path.parent.is_dir()):raise ProvisionError('Choose a new folder name inside an existing parent directory.')
        user=pwd.getpwnam('margin')
        if mode=='new':path.mkdir(mode=0o755);os.chown(path,user.pw_uid,user.pw_gid)
        self.grant(path,writable=(mode=='new'))
        reviews=path/'.reviews';managed=path if mode=='new' else path/'workspace'
        for target in {reviews,managed}:
            if target.is_symlink() or (target.exists() and not target.is_dir()):raise ProvisionError('The review or upload location is not a normal directory.')
            if not target.exists():target.mkdir(mode=0o755);os.chown(target,user.pw_uid,user.pw_gid)
            self.grant(target,writable=True)
        pid='ws-'+secrets.token_hex(8)
        mount=Path(self.config['mount_root'])/pid
        mount.mkdir(parents=True,exist_ok=False)
        info={'name':name,'description':'Personal server workspace','root':str(mount),'reviews':str(mount/'.reviews'),'writable_directory':'.' if mode=='new' else 'workspace','storage_limit_bytes':1073741824,'server_path':str(path),'owner_id':owner,'private':True,'pending':True}
        if 'default_agent_access' in self.config:
            info['agent_access']=dict(self.config['default_agent_access'])
            workspace_access.reconcile(info)
        registry=self.read_registry();registry[pid]=info;self.write_registry(registry)
        try:
            subprocess.run(['systemd-run','--quiet','--collect','--unit=margin-provision-'+pid,'--on-active=2s',sys.executable,str(Path(__file__).resolve()),'--config',self.config['config_path'],'--activate',pid],check=True)
        except Exception:
            info['error']='Unable to schedule folder activation. Ask the server administrator to retry.';registry[pid]=info;self.write_registry(registry);raise
        return {'id':pid,'pending':True,'name':name,'server_path':str(path)}

    def save_document(self, body):
        pid,relative,content,expected=(body.get(k) for k in ('project','path','content','revision'))
        if not isinstance(pid,str) or not isinstance(relative,str) or not isinstance(content,str) or not isinstance(expected,str):
            raise ProvisionError('Invalid document save request.')
        if len(content.encode())>2*1024*1024 or '\x00' in content:raise ProvisionError('Text exceeds the supported size.')
        sources=dict(self.config.get('document_sources',{}))
        sources.update({key:value['server_path'] for key,value in self.read_registry().items()})
        if pid not in sources:raise ProvisionError('Unknown document workspace.')
        parts=relative.split('/')
        if not relative or len(relative)>1000 or any(not part or part.startswith('.') or part in EXCLUDED or '\\' in part or any(ord(c)<32 for c in part) for part in parts):
            raise ProvisionError('Invalid document path.')
        target=Path(sources[pid])
        for part in parts:
            if target.is_symlink():raise ProvisionError('Linked paths are not available.')
            target=target/part
        if target.is_symlink() or not target.is_file() or target.suffix.lower() not in ('.md','.txt') or target.name.lower().endswith('.review.md'):
            raise ProvisionError('Only existing Markdown and text documents can be edited.')
        if target.stat().st_size>2*1024*1024:raise ProvisionError('Document is too large.')
        original=target.read_bytes();old=target.read_text(encoding='utf-8')
        if hashlib.sha256(old.encode()).hexdigest()!=expected:raise ProvisionError('Document changed since opening. Reload before saving; your draft is kept.')
        # Durable recovery copy precedes replacement, even if the HTTP request is interrupted.
        history=Path(self.config['document_history']);history.mkdir(mode=0o700,parents=True,exist_ok=True)
        key=hashlib.sha256((pid+'\0'+relative+'\0'+expected).encode()).hexdigest()
        backup=history/key
        if not backup.exists():
            with backup.open('xb') as out:out.write(original);out.flush();os.fsync(out.fileno())
            backup.chmod(0o600)
        stat=target.stat();fd,temp=tempfile.mkstemp(dir=target.parent,prefix='.margin-edit-')
        try:
            with os.fdopen(fd,'wb') as out:out.write(content.encode());out.flush();os.fsync(out.fileno())
            os.chown(temp,stat.st_uid,stat.st_gid);os.chmod(temp,stat.st_mode & 0o777)
            if target.is_symlink() or target.read_bytes()!=original:raise ProvisionError('Document changed while saving; retry with its latest version.')
            acl=subprocess.run(['getfacl','-cp','--',str(target)],check=True,capture_output=True).stdout
            subprocess.run(['setfacl','--set-file=-','--',temp],input=acl,check=True)
            subprocess.run(['setfacl','-m','u:margin:r--','--',temp],check=True)
            os.replace(temp,target)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        return {'revision':hashlib.sha256(content.encode()).hexdigest()}

    def activate(self, pid):
        registry=self.read_registry()
        if pid not in registry:raise ProvisionError('Unknown workspace.')
        def q(value):return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
        lines=['[Service]']
        for info in registry.values():
            source=Path(info['server_path']);target=Path(info['root'])
            if info['writable_directory']=='.':
                lines += ['BindPaths='+q(source)+':'+q(target),'ReadWritePaths='+q(target)]
            else:
                lines += ['BindReadOnlyPaths='+q(source)+':'+q(target)]
                for folder in ('.reviews','workspace'):
                    lines += ['BindPaths='+q(source/folder)+':'+q(target/folder),'ReadWritePaths='+q(target/folder)]
        dropin=Path(self.config['dropin']);dropin.parent.mkdir(parents=True,exist_ok=True)
        dropin.write_text('\n'.join(lines)+'\n')
        try:
            subprocess.run(['systemctl','daemon-reload'],check=True)
            subprocess.run(['systemctl','restart','margin.service'],check=True)
            registry[pid]['pending']=False;registry[pid].pop('error',None)
        except Exception:
            registry[pid]['error']='Folder activation failed. Contact the server administrator.'
            raise
        finally:self.write_registry(registry)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>(16*1024*1024 if self.path=='/save-document' else 8192):raise ProvisionError('Invalid request size.')
            body=json.loads(self.rfile.read(length))
            with open(self.server.broker.config['lock'],'a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                if self.path=='/browse':result=self.server.broker.browse(body.get('path'))
                elif self.path=='/provision':result=self.server.broker.provision(body)
                elif self.path=='/save-document':result=self.server.broker.save_document(body)
                else:raise ProvisionError('Unknown operation.')
            status=200
        except ProvisionError as exc:status=400;result={'error':str(exc)}
        except Exception:
            import traceback;traceback.print_exc();status=500;result={'error':'Server folder provisioning failed. Check the broker service log.'}
        encoded=json.dumps(result).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
    def log_message(self,*args):pass

class Server(socketserver.UnixStreamServer):pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--activate');args=parser.parse_args()
    config=json.loads(Path(args.config).read_text());config['config_path']=args.config
    broker=Broker(config)
    if args.activate:
        with open(config['lock'],'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);broker.activate(args.activate)
        return
    socket_path=Path(config['socket']);socket_path.parent.mkdir(parents=True,exist_ok=True)
    if socket_path.exists():socket_path.unlink()
    server=Server(str(socket_path),Handler);server.broker=broker
    user=pwd.getpwnam('margin');os.chown(socket_path,0,user.pw_gid);os.chmod(socket_path,0o660)
    server.serve_forever()

if __name__=='__main__':main()
