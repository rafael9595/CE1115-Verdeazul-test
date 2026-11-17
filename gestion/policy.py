from dataclasses import dataclass
from contextvars import ContextVar
from datetime import datetime
from django.db.models import Q
from django.utils import timezone
from .models import Account, Role, FarmAssignment, ReviewAssignment, OwnerLink, AuditorGrant, Version, Review, AuthSession

request_identity = ContextVar('request_identity', default=None)


def role_filter(role):
    return Q(role=role) | Q(additional_roles__contains=[role])


class DomainError(Exception):
    def __init__(self, message, rule='VALIDACION', status=400):
        super().__init__(message)
        self.rule, self.status = rule, status


def require(condition, message='Operación no autorizada.', rule='PERMISO', status=403):
    if not condition:
        raise DomainError(message, rule, status)


@dataclass(frozen=True)
class Actor:
    account: Account
    authenticated_at: datetime | None = None

    @property
    def person(self): return self.account.person
    @property
    def role(self):
        context = request_identity.get()
        if context and context['account_id'] == self.account.pk:
            return context['role']
        return self.person.role

    def recent(self):
        require(self.authenticated_at is not None and
                0 <= (timezone.now()-self.authenticated_at).total_seconds() <= 300,
                'Vuelva a autenticarse; esta operación exige autenticación de los últimos cinco minutos.', 'REAUTH')


def actor_for(account_id, authenticated_at=None, lock=False):
    qs = Account.objects.select_related('person')
    if lock:
        # Bloquear por separado: no arrastrar el LEFT JOIN nullable a FOR UPDATE.
        qs = Account.objects.select_for_update()
    try: account = qs.get(pk=account_id)
    except Account.DoesNotExist: raise DomainError('Sesión no válida.', 'C1', 401)
    require(account.is_active and account.person_id is not None, 'Cuenta no disponible.', 'C1', 401)
    context = request_identity.get()
    if context and context['account_id'] == account.pk:
        require(context['role'] in account.person.direct_roles and
                context['person_version'] == account.person.auth_version and
                context['credential_version'] == account.credential_version,
                'La sesión fue revocada. Inicie sesión nuevamente.', 'C1', 401)
        require(AuthSession.objects.filter(pk=context['session_id'],revoked_at__isnull=True).exists(),
                'La sesión fue revocada.', 'C1', 401)
    return Actor(account, authenticated_at)


def live(qs):
    now = timezone.now()
    return qs.filter(starts__lte=now).filter(Q(ends__isnull=True)|Q(ends__gt=now))


def assigned_tech(person, farm):
    return live(FarmAssignment.objects.filter(technician=person, farm=farm)).exists()


def assigned_reviewer(person, measurement):
    return live(ReviewAssignment.objects.filter(reviewer=person, measurement=measurement)).exists()


def owns(person, farm):
    return live(OwnerLink.objects.filter(person=person, owner_id=farm.owner_id)).exists()


def participated(person, measurement):
    return (Version.objects.filter(measurement=measurement, author=person).exists() or
            Review.objects.filter(version__measurement=measurement, reviewer=person).exists())


def technical_scope(actor, measurement):
    assigned = ((actor.role == Role.TECH and assigned_tech(actor.person, measurement.farm)) or
                (actor.role == Role.REVIEWER and assigned_reviewer(actor.person, measurement)))
    return assigned or participated(actor.person, measurement)


def can_read_measurement(actor, measurement):
    if actor.role in (Role.ADMIN,Role.MANAGER,Role.SUPERVISOR): return True
    if actor.role in (Role.TECH,Role.REVIEWER): return technical_scope(actor, measurement)
    if actor.role == Role.OWNER: return owns(actor.person, measurement.farm)
    return False


def can_report(actor, measurement):
    if actor.role == Role.AUDITOR:
        now=timezone.now()
        return AuditorGrant.objects.filter(auditor=actor.person, farm=measurement.farm,
                                           starts__lte=now, ends__gt=now).exists()
    return can_read_measurement(actor, measurement)


def can_download(actor, certificate):
    if actor.role in (Role.ADMIN,Role.MANAGER): return True
    if actor.role in (Role.TECH,Role.REVIEWER): return technical_scope(actor,certificate.review.version.measurement)
    if actor.role == Role.OWNER: return owns(actor.person,certificate.farm)
    return False
