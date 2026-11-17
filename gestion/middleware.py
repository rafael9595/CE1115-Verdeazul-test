from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from . import models as m
from .identity import digest, mfa_required, auditor_active
from .policy import request_identity, Actor
from .services import event


def identity_context(request):
    return {'active_role': getattr(request,'active_role','')}


class SessionPolicyMiddleware:
    def __init__(self,get_response):
        self.get_response = get_response

    def __call__(self,request):
        context_token = request_identity.set(None)
        try:
            response = None
            if request.user.is_authenticated:
                session = request.session
                account = request.user
                person = account.person
                now = timezone.now()
                timestamp = now.timestamp()
                role = session.get('active_role')
                record = m.AuthSession.objects.filter(key_digest=digest(session.session_key)).first()
                valid = (account.is_active and person is not None and record is not None and
                    record.account_id==account.pk and record.revoked_at is None and
                    session.get('auth_version')==person.auth_version and
                    session.get('credential_version')==account.credential_version and
                    role in person.direct_roles and record.role==role and
                    0<=timestamp-session.get('login_at',0)<=8*3600 and
                    0<=timestamp-session.get('last_activity',0)<=1800 and
                    (not mfa_required(account) or (session.get('mfa') and record.mfa)) and
                    auditor_active(person,role))
                if valid:
                    request.active_role = role
                    request_identity.set({'account_id':account.pk,'role':role,
                        'person_version':person.auth_version,'credential_version':account.credential_version,
                        'session_id':record.pk})
                    session['last_activity'] = timestamp
                    m.AuthSession.objects.filter(pk=record.pk,revoked_at__isnull=True).update(last_activity=now)
                    allowed = ('/identity/password/','/identity/mfa/','/reauth/','/logout/')
                    if account.must_change_password and not request.path.startswith(allowed):
                        response = (JsonResponse({'error':'Cambie la contraseña inicial.','rule':'O1'},status=403)
                            if request.path.startswith('/api/') else redirect('password_change'))
                else:
                    if record and record.revoked_at is None:
                        m.AuthSession.objects.filter(pk=record.pk).update(revoked_at=now)
                    if person is not None:
                        event(Actor(account),'SESION_FINALIZADA',record.pk if record else '',rule='C1')
                    logout(request)
            if response is None:
                response = self.get_response(request)
            response['Cache-Control'] = 'no-store'
            response['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
            response['Referrer-Policy'] = 'same-origin'
            return response
        finally:
            request_identity.reset(context_token)
