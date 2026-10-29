"""Configure and repair per-workspace local-agent ACLs. Run on the host as root.

With no options, enable root (the server operator) on
current workspaces and future workspaces. Existing assignments are preserved.
For a dedicated non-root agent, explicitly select a workspace, account and role.
No web user is automatically mapped to a local OS account.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workspace_access


def write_json(path, value):
    st = path.stat()
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.access-config-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.chown(temp, st.st_uid, st.st_gid);os.chmod(temp, st.st_mode & 0o777)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project');parser.add_argument('--agent');parser.add_argument('--role', choices=['read','write'])
    args = parser.parse_args()
    if os.geteuid() != 0:parser.error('Run as root on the host.')
    if any((args.project,args.agent,args.role)) and not all((args.project,args.agent,args.role)):
        parser.error('--project, --agent and --role must be supplied together.')
    if args.agent:
        account = pwd.getpwnam(args.agent)
        if account.pw_uid != 0 and account.pw_uid < 1000:
            parser.error('Use a dedicated agent login account, not a service account.')
    config_path=Path('/etc/margin/config.json');broker_path=Path('/etc/margin/broker.json')
    broker=json.loads(broker_path.read_text())
    with open(broker['lock'],'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        config=json.loads(config_path.read_text());registry_path=Path(broker['registry']);registry=json.loads(registry_path.read_text())
        projects={**config['projects'],**registry}
        if args.project and args.project not in projects:parser.error('Unknown workspace ID.')
        backup=Path('/var/lib/margin/backups')/('agent-access-'+str(time.time_ns()));backup.mkdir(mode=0o700,parents=True)
        for path in (config_path,broker_path,registry_path):shutil.copy2(path,backup/path.name)
        with sqlite3.connect('file:'+config['database']+'?mode=ro',uri=True) as live,sqlite3.connect(backup/'margin.sqlite') as saved:live.backup(saved)
        (backup/'margin.sqlite').chmod(0o600)
        print('Recovery backup:',backup,flush=True)
        selected={args.project:projects[args.project]} if args.project else projects
        for pid,info in selected.items():
            info.setdefault('agent_access',{})[args.agent or 'root']=args.role or 'write'
            workspace_access.identities(info['agent_access'])
            source=Path(info.get('server_path',info['root']))
            # Do not open protected parents such as /root: even traversal could
            # expose unrelated world-readable siblings. Use a scoped mount instead.
            if args.agent and pwd.getpwnam(args.agent).pw_uid != 0:
                allowed=subprocess.run(['runuser','-u',args.agent,'--','test','-x',str(source.parent)],capture_output=True).returncode == 0
                if not allowed:
                    raise SystemExit('The agent cannot traverse the workspace parent. Provide a scoped mount in its environment; no parent permissions were changed.')
            acl_path=backup/(pid+'.acls.jsonl')
            with acl_path.open('w') as snapshots:
                def snapshot(fd, relative):
                    st=os.fstat(fd)
                    acl=subprocess.run(['getfacl','-cpn','--',f'/proc/self/fd/{fd}'],pass_fds=(fd,),check=True,capture_output=True).stdout.decode()
                    snapshots.write(json.dumps({'path':str(source/relative),'uid':st.st_uid,'gid':st.st_gid,'mode':st.st_mode & 0o7777,'acl':acl})+'\n');snapshots.flush()
                count=workspace_access.reconcile(info,snapshot=snapshot)
            print(pid+': reconciled '+str(count)+' files/directories; agents '+', '.join(info['agent_access']))
        if not args.project:broker.setdefault('default_agent_access',{}).setdefault('root','write')
        write_json(config_path,config);write_json(registry_path,registry);write_json(broker_path,broker)
    subprocess.run(['systemctl','restart','margin-broker.service'],check=True)
    subprocess.run(['systemctl','kill','--kill-whom=main','--signal=HUP','margin.service'],check=True)
    print('Configuration, ACL and database backup:',backup)

if __name__=='__main__':main()
