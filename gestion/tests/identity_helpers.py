"""Sesiones explícitas para pruebas de negocio; no desactiva middleware de producción."""
import pyotp
from django.test import Client
from django.utils import timezone
from gestion import identity as i, models as m


def factor(account):
    device=m.MFADevice.objects.filter(account=account,confirmed=True).first()
    if device:
        return i.decrypt(device)
    secret=pyotp.random_base32()
    m.MFADevice.objects.create(account=account,confirmed=True,
        encrypted_secret=i.cipher().encrypt(secret.encode()).decode())
    return secret


def session_for(account,csrf=False,mfa=True,role=None):
    account.refresh_from_db()
    client=Client(enforce_csrf_checks=csrf)
    client.force_login(account)
    session=client.session
    now=timezone.now().timestamp()
    role=role or account.person.role
    if mfa:
        factor(account)
    session.update({'login_at':now,'last_activity':now,'reauth_at':now,
        'auth_version':account.person.auth_version,'credential_version':account.credential_version,
        'active_role':role,'mfa':mfa})
    session.save()
    m.AuthSession.objects.create(account=account,key_digest=i.digest(session.session_key),role=role,mfa=mfa)
    return client
