"""Identidad compartida, autenticación y administración O1/O15.

Los secretos solo se devuelven durante su entrega inicial. Las decisiones y
revocaciones usan PostgreSQL; no dependen de memoria de un worker.
"""
import hashlib
import hmac
import re
import secrets
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone
from . import models as m
from .policy import Actor, DomainError, actor_for, require, role_filter, live
from .services import event, reason, _keys

MFA_ROLES = {m.Role.ADMIN, m.Role.MANAGER, m.Role.SUPERVISOR,
             m.Role.REVIEWER, m.Role.SECURITY, m.Role.AUDITOR}


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def cipher():
    try:
        raw = Path(settings.IDENTITY_KEY_FILE).read_bytes()
        if len(raw) > 128:
            raise ValueError()
        return Fernet(raw.strip())
    except (OSError, ValueError, TypeError):
        raise DomainError('No se pudo cargar la clave de protección de identidad.', 'SECRETOS', 503)


def decrypt(device):
    try:
        return cipher().decrypt(device.encrypted_secret.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise DomainError('No se pudo abrir el segundo factor. Revise la clave de identidad.', 'SECRETOS', 503)


def mfa_required(account):
    return bool(account.person.effective_roles & MFA_ROLES) or m.MFADevice.objects.filter(account=account, confirmed=True).exists()


def auditor_active(person, role):
    return role != m.Role.AUDITOR or live(m.AuditorGrant.objects.filter(auditor=person)).exists()


@contextmanager
def locked_accounts(*account_ids):
    """Mismo orden de bloqueo que captura/gestión: personas, luego cuentas."""
    with transaction.atomic():
        ids = list(m.Account.objects.filter(pk__in=account_ids).values_list('person_id', flat=True))
        list(m.Person.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
        accounts = list(m.Account.objects.select_for_update().filter(pk__in=account_ids).order_by('pk'))
        yield {a.pk: a for a in accounts}


def throttle_key(account=None, username=''):
    return digest('identity:' + (str(account.person_id) if account else username.casefold()[:150]))


def throttle(key):
    m.AuthThrottle.objects.get_or_create(key=key)
    return m.AuthThrottle.objects.select_for_update().get(pk=key)


def blocked(row):
    return row.locked_until is not None and row.locked_until > timezone.now()


def failed(row, account=None):
    now = timezone.now()
    if now - row.window_start >= timedelta(minutes=15):
        row.window_start, row.failures, row.locked_until = now, 0, None
    row.failures += 1
    if row.failures >= 10:
        row.locked_until = now + timedelta(minutes=15)
    row.save()
    m.Event.objects.create(actor=account.person if account else None,
        account_id_at_event=str(account.pk) if account else '',
        role=account.person.role if account else '', action='AUTENTICACION_FALLIDA',
        result='DENEGADO', rule='P-10', detail={'pausa': row.failures >= 10})


def clear_throttle(account):
    m.AuthThrottle.objects.filter(key=throttle_key(account)).update(
        failures=0, window_start=timezone.now(), locked_until=None)


def password_check(username, password):
    """Nunca devuelve una sesión; faltan MFA y las políticas de acceso."""
    account = m.Account.objects.filter(username__iexact=username[:150]).first()
    if account is None or account.person_id is None:
        with transaction.atomic():
            row = throttle(throttle_key(username=username))
            if not blocked(row):
                m.Account().set_password(password[:128])  # costo sin revelar existencia
                failed(row)
        return None
    with locked_accounts(account.pk) as accounts:
        account = accounts[account.pk]
        row = throttle(throttle_key(account))
        if blocked(row):
            return None
        if len(password) <= 128 and account.is_active and account.check_password(password):
            return account
        failed(row, account)
    return None


def set_pending(request, account):
    if request.session.session_key:
        m.AuthSession.objects.filter(key_digest=digest(request.session.session_key),revoked_at__isnull=True).update(revoked_at=timezone.now())
    request.session.flush()
    request.session.update({'pending_account': account.pk, 'pending_at': timezone.now().timestamp(),
        'pending_person_version': account.person.auth_version,
        'pending_credential_version': account.credential_version,
        'pending_hash': account.get_session_auth_hash()})


def pending_account(request):
    account = m.Account.objects.select_related('person').filter(pk=request.session.get('pending_account')).first()
    valid = (account and account.is_active and account.person_id and
        0 <= timezone.now().timestamp() - request.session.get('pending_at', 0) <= 300 and
        request.session.get('pending_person_version') == account.person.auth_version and
        request.session.get('pending_credential_version') == account.credential_version and
        hmac.compare_digest(request.session.get('pending_hash', ''), account.get_session_auth_hash()))
    require(valid, 'Vuelva a iniciar sesión para completar la autenticación.', 'C1', 401)
    return account


def new_recovery_codes(account):
    m.RecoveryCode.objects.filter(account=account, used_at__isnull=True).update(used_at=timezone.now())
    codes = [secrets.token_hex(16) for _ in range(8)]
    m.RecoveryCode.objects.bulk_create([m.RecoveryCode(account=account, digest=digest(c)) for c in codes])
    return codes


def verify_factor_locked(account, code):
    """Invocar con persona/cuenta bloqueadas. Los reintentos no reutilizan OTP."""
    code = code.strip()
    device = m.MFADevice.objects.select_for_update().filter(account=account, confirmed=True).first()
    if device is None:
        return False
    if re.fullmatch(r'\d{6}', code):
        current = int(timezone.now().timestamp()) // 30
        otp = pyotp.TOTP(decrypt(device))
        for counter in (current, current - 1, current + 1):
            if counter > device.last_counter and hmac.compare_digest(otp.at(counter * 30), code):
                device.last_counter = counter
                device.save(update_fields=['last_counter'])
                return True
    elif re.fullmatch(r'[0-9a-f]{32}', code):
        recovery = m.RecoveryCode.objects.select_for_update().filter(account=account, digest=digest(code), used_at__isnull=True).first()
        if recovery:
            recovery.used_at = timezone.now()
            recovery.save(update_fields=['used_at'])
            event(Actor(account), 'CODIGO_RECUPERACION_USADO', account.pk)
            return True
    return False


def factor_check(account_id, code, password=None):
    with locked_accounts(account_id) as accounts:
        account = accounts[account_id]
        row = throttle(throttle_key(account))
        if blocked(row) or not account.is_active:
            return False
        if (password is None or (len(password) <= 128 and account.check_password(password))) and verify_factor_locked(account, code):
            clear_throttle(account)
            return True
        failed(row, account)
        return False


def start_session(request, account, mfa=False, role=None):
    account.refresh_from_db()
    role = role or account.person.role
    require(account.is_active and role in account.person.direct_roles, rule='C1')
    require(not mfa_required(account) or mfa, 'Se requiere segundo factor.', 'C1', 401)
    require(auditor_active(account.person, role), 'El encargo del auditor no está vigente.', 'C6', 403)
    login(request, account, backend='django.contrib.auth.backends.ModelBackend')
    for key in list(request.session.keys()):
        if key.startswith('pending_'):
            del request.session[key]
    now = timezone.now().timestamp()
    request.session.update({'login_at': now, 'last_activity': now, 'reauth_at': now,
        'auth_version': account.person.auth_version, 'credential_version': account.credential_version,
        'mfa': mfa, 'active_role': role})
    request.session.save()
    m.AuthSession.objects.create(account=account, key_digest=digest(request.session.session_key), role=role, mfa=mfa)
    clear_throttle(account)
    event(Actor(account), 'LOGIN_OK', detail={'mfa': mfa, 'active_role': role})


def revoke_account(account, action='SESIONES_REVOCADAS'):
    m.AuthSession.objects.filter(account=account, revoked_at__isnull=True).update(revoked_at=timezone.now())
    # La versión de cuenta protege incluso una solicitud que ya pasó por middleware.
    m.Account.objects.filter(pk=account.pk).update(credential_version=F('credential_version') + 1)
    account.refresh_from_db()


def breach_count(password):
    """Solo envía los cinco primeros caracteres del hash; no guarda la consulta."""
    hashed = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
    request = Request('https://api.pwnedpasswords.com/range/' + hashed[:5],
        headers={'Add-Padding': 'true', 'User-Agent': 'Verdeazul-Identity/4.0'})
    try:
        with urlopen(request, timeout=6) as response:
            if response.status != 200:
                raise ValueError()
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError()
        rows = raw.decode('ascii').splitlines()
        require(bool(rows), 'No se pudo comprobar la contraseña.', 'CONTRASENA', 503)
        found = 0
        for line in rows:
            suffix, count = line.split(':')
            if not re.fullmatch('[A-F0-9]{35}', suffix) or not count.isdigit():
                raise ValueError()
            if hmac.compare_digest(suffix, hashed[5:]):
                found = int(count)
        return found
    except DomainError:
        raise
    except Exception:
        raise DomainError('No se pudo consultar la lista de contraseñas comprometidas. Reintente con conexión; la contraseña no se cambió.', 'CONTRASENA', 503)


def validate_new_password(account, password):
    require(isinstance(password, str) and 15 <= len(password) <= 128,
            'Utilice entre 15 y 128 caracteres.', 'CONTRASENA', 400)
    try:
        validate_password(password, account)
    except ValidationError as exc:
        raise DomainError(' '.join(exc.messages), 'CONTRASENA', 400)
    require(not breach_count(password), 'Esa contraseña aparece en filtraciones conocidas. Elija otra.', 'CONTRASENA', 400)


def validate_roles(primary, additional):
    require(isinstance(additional, list) and all(isinstance(x, str) for x in additional), rule='ROLES', status=400)
    roles = {primary, *additional}
    require(roles <= set(m.Role.values) and primary in m.Role.values, 'Rol desconocido.', 'ROLES', 400)
    require(not {m.Role.TECH, m.Role.REVIEWER} <= roles,
            'Una persona no puede ser técnico y verificador simultáneamente.', 'R-SoD-01', 403)
    return sorted(roles - {primary})


def require_sensitive(request):
    actor = actor_for(request.user.pk)
    when = request.session.get('reauth_at', 0)
    require(request.session.get('mfa') and 0 <= timezone.now().timestamp() - when <= 300,
            'Renueve su autenticación con contraseña y segundo factor.', 'REAUTH', 403)
    return actor


def safe_profile(account):
    return {'id': account.pk, 'username': account.username, 'first_name': account.first_name,
        'last_name': account.last_name, 'email': account.email, 'active': account.is_active,
        'person_id': str(account.person_id), 'work_id': account.person.work_id,
        'primary_role': account.person.role, 'roles': sorted(account.person.direct_roles),
        'effective_roles': sorted(account.person.effective_roles),
        'mfa_enabled': m.MFADevice.objects.filter(account=account, confirmed=True).exists(),
        'must_change_password': account.must_change_password}


def account_list(account_id):
    actor = actor_for(account_id)
    require(actor.role == m.Role.ADMIN, rule='O1')
    event(actor, 'CUENTAS_CONSULTADAS', rule='O1')
    return [safe_profile(a) for a in m.Account.objects.filter(person__isnull=False).select_related('person').order_by('username')]


def session_list(request):
    actor = actor_for(request.user.pk)
    rows = m.AuthSession.objects.select_related('account__person').order_by('-created_at')
    if actor.role not in (m.Role.ADMIN, m.Role.SECURITY):
        rows = rows.filter(account__person=actor.person)
    now = timezone.now()
    output = []
    for row in rows[:500]:
        status = 'REVOCADA' if row.revoked_at else ('VENCIDA' if
            now - row.created_at > timedelta(hours=8) or now - row.last_activity > timedelta(minutes=30) else 'ACTIVA')
        output.append({'id': str(row.pk), 'work_id': row.account.person.work_id,
            'account_id': row.account_id, 'role': row.role, 'mfa': row.mfa,
            'created_at': row.created_at.isoformat(), 'last_activity': row.last_activity.isoformat(), 'status': status,
            'current': hmac.compare_digest(row.key_digest, digest(request.session.session_key)),
            'can_revoke': actor.role == m.Role.ADMIN or (actor.role != m.Role.SECURITY and row.account.person_id == actor.person.pk)})
    event(actor, 'SESIONES_CONSULTADAS', rule='O15')
    return output


def issue_ticket(actor, target, purpose, reset_mfa=False):
    now = timezone.now()
    m.CredentialTicket.objects.filter(account=target, used_at__isnull=True).update(used_at=now)
    revoke_account(target)
    token = secrets.token_urlsafe(32)
    m.CredentialTicket.objects.create(account=target, digest=digest(token), purpose=purpose,
        reset_mfa=reset_mfa, expires_at=now + timedelta(minutes=30), issued_by=actor.person,
        credential_version=target.credential_version, person_auth_version=target.person.auth_version)
    return token


def end_assignments(person, actor, removed, why, all_access=False):
    now = timezone.now()
    if all_access or m.Role.TECH in removed:
        live(m.FarmAssignment.objects.filter(technician=person)).update(ends=now, revoked_by=actor.person, revocation_reason=why)
    if all_access or m.Role.REVIEWER in removed:
        live(m.ReviewAssignment.objects.filter(reviewer=person)).update(ends=now, revoked_by=actor.person, revocation_reason=why)
    if all_access or m.Role.OWNER in removed:
        live(m.OwnerLink.objects.filter(person=person)).update(ends=now)
    if all_access or m.Role.AUDITOR in removed:
        live(m.AuditorGrant.objects.filter(auditor=person)).update(ends=now)


def admin_action(request, action, target_id, data):
    actor = require_sensitive(request)
    require(actor.role == m.Role.ADMIN, rule='O1')
    allowed = {
        'create': {'username','work_id','primary_role','additional_roles','first_name','last_name','email','reason','verification_reference'},
        'roles': {'primary_role','additional_roles','reason','expected_version'},
        'profile': {'first_name','last_name','email','reason'},
        'disable': {'reason'}, 'enable': {'reason'},
        'recovery': {'reason','verification_reference','reset_mfa'},
        'grant': {'farm_id','assignment_name','ends','reason'},
    }
    require(action in allowed, rule='O1', status=400)
    _keys(data, allowed[action])
    why = reason(data)
    try:
        with transaction.atomic():
            # Serializa cambios administrativos para no retirar concurrentemente el último administrador.
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [1115001])
            target = m.Account.objects.filter(pk=target_id).first() if action != 'create' else None
            ids = {actor.person.pk}
            if target:
                ids.add(target.person_id)
            if action == 'create':
                work_id = str(data.get('work_id','')).strip().upper()
                require(re.fullmatch(r'[A-Z0-9_-]{3,60}', work_id), 'Identidad laboral inválida.', 'O1', 400)
                existing_person = m.Person.objects.filter(work_id__iexact=work_id).first()
                if existing_person:
                    ids.add(existing_person.pk)
            list(m.Person.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
            actor = actor_for(request.user.pk, lock=True)
            if target:
                target = m.Account.objects.select_for_update().get(pk=target.pk)
            if action == 'create':
                username = str(data.get('username','')).strip().lower()
                require(re.fullmatch(r'[a-z0-9_.-]{3,100}', username), 'Usuario: 3–100 letras, números, punto, guion o guion bajo.', 'O1', 400)
                require(not m.Account.objects.filter(username__iexact=username).exists(), 'El usuario ya existe.', 'O1', 409)
                reference = reason(data, 'verification_reference')
                primary = data.get('primary_role')
                additional = validate_roles(primary, data.get('additional_roles', []))
                if existing_person:
                    require(m.Account.objects.filter(person=existing_person,is_active=True).exists(),
                            'La persona está deshabilitada. Habilítela antes de crear otra cuenta.', 'O1', 409)
                    require(existing_person.role == primary and existing_person.additional_roles == additional,
                            'Las cuentas de una misma persona comparten sus roles. Modifique primero los roles de la persona.', 'R-SoD-01', 409)
                    person = existing_person
                else:
                    person = m.Person.objects.create(work_id=work_id, role=primary, additional_roles=additional)
                target = m.Account(username=username, person=person, must_change_password=True)
                target.set_unusable_password()
                target.save()
                _profile_fields(target, data, legal=True)
                token = issue_ticket(actor, target, 'ACTIVACION', reset_mfa=True)
                event(actor, 'CUENTA_CREADA', target.pk, rule='O1', detail={'reason':why,'verification_reference':reference,'person_id':str(person.pk),'roles':sorted(person.direct_roles)})
                return {'account_id':target.pk,'activation_code':token,'expires_minutes':30}
            require(target is not None and target.person_id, 'Cuenta no disponible.', 'O1', 404)
            if action in ('roles','disable'):
                current = target.person
                removes_admin = action == 'disable' or m.Role.ADMIN not in {data.get('primary_role'), *data.get('additional_roles', [])}
                if m.Role.ADMIN in current.direct_roles and removes_admin:
                    require(m.Account.objects.filter(Q(person__role=m.Role.ADMIN)|Q(person__additional_roles__contains=[m.Role.ADMIN]),
                            is_active=True, must_change_password=False, password__startswith='argon2$',
                            mfa_device__confirmed=True).exclude(person=current).exists(),
                            'Debe conservar otro administrador activo con contraseña individual y segundo factor configurados.', 'O1', 409)
            if action == 'roles':
                person = target.person
                require(str(data.get('expected_version')) == str(person.auth_version), 'Los roles cambiaron. Actualice la página.', 'CONFLICTO', 409)
                additional = validate_roles(data.get('primary_role'), data.get('additional_roles', []))
                previous = person.direct_roles
                person.role, person.additional_roles = data['primary_role'], additional
                person.save(update_fields=['role','additional_roles'])
                end_assignments(person, actor, previous-person.direct_roles, why)
                m.AuthSession.objects.filter(account__person=person,revoked_at__isnull=True).update(revoked_at=timezone.now())
                event(actor,'ROLES_MODIFICADOS',person.pk,rule='R-SoD-01',detail={'before':sorted(previous),'after':sorted(person.direct_roles),'reason':why})
            elif action in ('disable','enable'):
                # La baja es por persona; una segunda cuenta no conserva el acceso.
                person = target.person
                m.Account.objects.filter(person=person).update(is_active=action=='enable')
                m.Person.objects.filter(pk=person.pk).update(auth_version=F('auth_version')+1)
                m.AuthSession.objects.filter(account__person=person,revoked_at__isnull=True).update(revoked_at=timezone.now())
                if action == 'disable':
                    end_assignments(person, actor, set(), why, all_access=True)
                event(actor,'PERSONA_'+('DESHABILITADA' if action=='disable' else 'HABILITADA'),person.pk,rule='P-09',detail={'reason':why})
            elif action == 'profile':
                _profile_fields(target, data, legal=True)
                event(actor,'PERFIL_ADMINISTRADO',target.pk,rule='O1',detail={'reason':why})
            elif action == 'recovery':
                reference = reason(data,'verification_reference')
                require(target.is_active, 'La cuenta está deshabilitada.', 'O1', 409)
                require(isinstance(data.get('reset_mfa',False),bool),'Valor de recuperación inválido.','O1',400)
                reset = data.get('reset_mfa',False)
                token = issue_ticket(actor,target,'RECUPERACION',reset)
                event(actor,'RECUPERACION_AUTORIZADA',target.pk,rule='O1',detail={'reason':why,'verification_reference':reference,'reset_mfa':reset})
                return {'account_id':target.pk,'activation_code':token,'expires_minutes':30}
            elif action == 'grant':
                from django.utils.dateparse import parse_datetime
                require(m.Role.AUDITOR in target.person.direct_roles,rule='C6')
                end = parse_datetime(str(data.get('ends','')))
                require(end is not None and timezone.is_aware(end) and end>timezone.now(),'Indique vencimiento futuro con zona horaria.','C6',400)
                farm = m.Farm.objects.get(pk=data.get('farm_id'))
                name = reason(data,'assignment_name')
                require(len(name)<=100,rule='CAMPOS',status=400)
                # Extensiones como nuevos encargos: la fila histórica conserva su vencimiento.
                grant = m.AuditorGrant.objects.create(auditor=target.person,farm=farm,assignment_name=name,ends=end)
                event(actor,'ENCARGO_AUDITOR_AUTORIZADO',grant.pk,rule='C6',detail={'reason':why,'person_id':str(target.person_id),'farm_id':str(farm.pk),'ends':end.isoformat()})
            return {'status':'OK'}
    except (m.Account.DoesNotExist, m.Farm.DoesNotExist, ValidationError):
        raise DomainError('Objeto o datos no disponibles.','O1',400)


def _profile_fields(account, data, legal=False):
    from django.core.validators import validate_email
    fields = ['email'] + (['first_name','last_name'] if legal else [])
    for field in fields:
        if field in data:
            value = data[field]
            require(isinstance(value,str) and len(value)<=150,'Campo de perfil inválido.','O1',400)
            if field == 'email' and value:
                try:
                    validate_email(value)
                except ValidationError:
                    raise DomainError('Correo de contacto inválido.','O1',400)
            setattr(account,field,value.strip())
    account.save(update_fields=fields)


def redeem_ticket(request, token, password, factor):
    ticket = m.CredentialTicket.objects.select_related('account__person').filter(digest=digest(token)).first()
    require(ticket is not None, 'Código inválido, utilizado o vencido.', 'RECUPERACION', 400)
    validate_new_password(ticket.account, password)
    with locked_accounts(ticket.account_id) as accounts:
        account = accounts[ticket.account_id]
        ticket = m.CredentialTicket.objects.select_for_update().get(pk=ticket.pk)
        valid = (account.is_active and ticket.used_at is None and ticket.expires_at > timezone.now()
            and ticket.credential_version == account.credential_version and ticket.person_auth_version == account.person.auth_version)
        require(valid, 'Código inválido, utilizado o vencido.', 'RECUPERACION', 400)
        row = throttle(throttle_key(account))
        if blocked(row):
            return None
        if not ticket.reset_mfa and not verify_factor_locked(account, factor):
            failed(row, account)
            return None
        account.set_password(password)
        account.must_change_password = False
        account.save(update_fields=['password','must_change_password'])
        revoke_account(account)
        if ticket.reset_mfa:
            m.MFADevice.objects.filter(account=account).delete()
            m.RecoveryCode.objects.filter(account=account,used_at__isnull=True).update(used_at=timezone.now())
        ticket.used_at = timezone.now()
        ticket.save(update_fields=['used_at'])
        event(Actor(account), 'CREDENCIALES_RECUPERADAS', account.pk, rule='O1', detail={'purpose':ticket.purpose,'mfa_reset':ticket.reset_mfa})
        clear_throttle(account)
        set_pending(request, account)
        return account
