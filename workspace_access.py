"""Linux ACL policy for explicitly assigned local workspace agents.

Web logins are never Linux identities. Configuration is administrator-owned.
Use directory defaults for inheritance and explicit ACLs before publishing files.
"""
import os
from pathlib import Path
import pwd
import stat
import subprocess

EXCLUDED = {'.git', 'node_modules', 'external', 'venv', '__pycache__', 'vendor', 'dist', 'build'}


def identities(agents):
    if not isinstance(agents, dict):
        raise ValueError('agent_access must map Linux usernames to read or write.')
    result = {}
    for username, role in agents.items():
        if role not in ('read', 'write'):
            raise ValueError('Agent access must be read or write.')
        uid = pwd.getpwnam(username).pw_uid
        result[uid] = role
    return result


def open_path(path):
    """Open each component without following symlinks, including ancestors."""
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('Parent traversal is not allowed.')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for i, part in enumerate(path.parts[1:]):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if i < len(path.parts)-2:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def merge_source_acl(fd, named, directory):
    """Preserve effective existing rights when adding a wider ACL mask."""
    raw = subprocess.run(['getfacl', '-cpn', '--', f'/proc/self/fd/{fd}'], pass_fds=(fd,), check=True, capture_output=True).stdout.decode()
    scopes = {'': {}, 'default:': {}}
    for line in raw.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        scope = 'default:' if line.startswith('default:') else ''
        key, permissions = line[len(scope):].rsplit(':', 1)
        scopes[scope][key] = permissions
    for entries in scopes.values():
        mask = entries.get('mask:', 'rwx')
        for key, permissions in list(entries.items()):
            if key.startswith('group:') or (key.startswith('user:') and key != 'user:'):
                entries[key] = ''.join(c if c in mask else '-' for c in permissions)
    if directory and not scopes['default:']:
        scopes['default:'] = {key: scopes[''][key] for key in ('user:', 'group:', 'other:')}
    for scope in (('', 'default:') if directory else ('',)):
        entries = scopes[scope]
        for line in named:
            key, permissions = line.rsplit(':', 1)
            entries[key] = permissions
        rights = ''.join(value for key, value in entries.items() if key.startswith('group:') or (key.startswith('user:') and key != 'user:'))
        entries['mask:'] = ''.join(c if c in rights else '-' for c in 'rwx')
    return [scope+key+':'+permissions for scope, entries in scopes.items() for key, permissions in entries.items()]


def set_acl(fd, agents, *, reviews=False, private=True, service_uid=None):
    info = os.fstat(fd)
    directory = stat.S_ISDIR(info.st_mode)
    if not directory and not stat.S_ISREG(info.st_mode):
        raise ValueError('Only regular files and directories can receive workspace access.')
    if not directory and info.st_nlink > 1:
        raise ValueError('Refusing to change permissions on a multiply linked file.')
    entries = {}
    for uid, role in agents.items():
        writable = role == 'write' and not reviews
        entries[uid] = ('rwx' if writable else 'r-x') if directory else ('rw-' if writable else 'r--')
        if not directory and info.st_mode & 0o111:
            entries[uid] = entries[uid][:2] + 'x'
    if private:
        service_uid = pwd.getpwnam('margin').pw_uid if service_uid is None else service_uid
        entries[service_uid] = 'rwx' if directory else 'rw-'
    named = [f'user:{uid}:{permission}' for uid, permission in sorted(entries.items())]
    if private:
        # The owner and service retain writes; unrelated local users have no access.
        owner = 'rwx' if directory or info.st_mode & 0o111 else 'rw-'
        lines = [f'user::{owner}', *named, 'group::---', 'mask::rwx' if directory or info.st_mode & 0o111 else 'mask::rw-', 'other::---']
        if directory:
            lines += ['default:'+line for line in ['user::rwx', *named, 'group::---', 'mask::rwx', 'other::---']]
        option = '--set-file=-'
    else:
        # Imported sources keep their existing owner, group and other permissions.
        lines = merge_source_acl(fd, named, directory)
        option = '--set-file=-'
    if lines:
        subprocess.run(['setfacl', option, '--', f'/proc/self/fd/{fd}'], input=('\n'.join(lines)+'\n').encode(), pass_fds=(fd,), check=True, capture_output=True)


def apply(path, info, *, reviews=False):
    """Set a new managed inode's policy before making its bytes visible."""
    if 'agent_access' not in info:
        return False
    agents = identities(info['agent_access'])
    fd = open_path(path)
    try:
        set_acl(fd, agents, reviews=reviews)
    finally:
        os.close(fd)
    return True


def reconcile(info, *, service_uid=None, snapshot=None):
    """Repair current content and set defaults; never follow links out of a workspace.

    snapshot(fd, relative) can persist an ACL backup before each modification.
    Hidden source content and generated dependencies are not granted to agents.
    Trash is not exposed. Existing non-managed source permissions are retained.
    """
    agents = identities(info['agent_access'])
    root = Path(info.get('server_path', info['root']))
    managed = info.get('writable_directory')
    fd = open_path(root)
    count = 0
    try:
        device = os.fstat(fd).st_dev
        def walk(current, relative):
            nonlocal count
            st = os.fstat(current)
            if st.st_dev != device:
                raise ValueError('Nested filesystem mounts must be separate workspaces.')
            if not stat.S_ISDIR(st.st_mode) and not stat.S_ISREG(st.st_mode):
                return
            count += 1
            if count > 100000:
                raise ValueError('Workspace exceeds the permission repair limit.')
            reviews = relative == '.reviews' or relative.startswith('.reviews/')
            private = reviews or managed == '.' or (managed and (relative == managed or relative.startswith(managed+'/')))
            if snapshot:
                snapshot(current, relative)
            set_acl(current, agents, reviews=reviews, private=bool(private), service_uid=service_uid)
            if stat.S_ISDIR(st.st_mode):
                for name in os.listdir(current):
                    if (name.startswith('.') and not (relative == '' and name == '.reviews')) or name in EXCLUDED:
                        continue
                    entry = os.stat(name, dir_fd=current, follow_symlinks=False)
                    if not stat.S_ISDIR(entry.st_mode) and not stat.S_ISREG(entry.st_mode):
                        continue
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
                    try:
                        walk(child, relative+'/'+name if relative else name)
                    finally:
                        os.close(child)
        walk(fd, '')
    finally:
        os.close(fd)
    return count
