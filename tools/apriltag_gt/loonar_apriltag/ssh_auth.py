"""Noninteractive SSH authentication using a user-local password file."""
from pathlib import Path
import shutil

PASSWORD_FILE = Path.home() / '.config/loonar/ssh-password'


def authenticated(tool, password_file=PASSWORD_FILE):
    if not shutil.which('sshpass'):
        raise RuntimeError('sshpass is required for password-file SSH authentication')
    if not password_file.is_file():
        raise RuntimeError(f'Missing SSH password file: {password_file}')
    if password_file.stat().st_mode & 0o077:
        raise RuntimeError(f'SSH password file must have mode 600: {password_file}')
    return ['sshpass', '-f', str(password_file), tool]
