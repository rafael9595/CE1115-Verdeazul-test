import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Role(models.TextChoices):
    TECH = 'TECNICO', 'Técnico'
    REVIEWER = 'VERIFICADOR', 'Verificador'
    ADMIN = 'ADMINISTRADOR', 'Administrador'
    AUDITOR = 'AUDITOR', 'Auditor'
    OWNER = 'PROPIETARIO', 'Propietario'
    MANAGER = 'GERENTE', 'Gerente'
    SUPERVISOR = 'SUPERVISOR', 'Supervisor'
    SECURITY = 'SEGURIDAD', 'Seguridad'


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Meta:
        abstract = True


class Person(Entity):
    work_id = models.CharField(max_length=60, unique=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    auth_version = models.PositiveIntegerField(default=1)
    additional_roles = models.JSONField(default=list, blank=True)

    @property
    def direct_roles(self):
        return {self.role, *self.additional_roles}

    @property
    def effective_roles(self):
        roles = self.direct_roles
        if Role.ADMIN in roles:
            roles |= {Role.MANAGER, Role.SUPERVISOR, Role.SECURITY}
        return roles
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(role__in=Role.values), name='valid_person_role')]


class Account(AbstractUser):
    person = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='accounts')
    credential_version = models.PositiveIntegerField(default=1)
    must_change_password = models.BooleanField(default=False)


class AuthSession(Entity):
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    key_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    mfa = models.BooleanField(default=False)


class AuthThrottle(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window_start = models.DateTimeField(default=timezone.now)
    failures = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True)


class MFADevice(Entity):
    account = models.OneToOneField(Account, on_delete=models.PROTECT, related_name='mfa_device')
    encrypted_secret = models.TextField()
    confirmed = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=-1)
    created_at = models.DateTimeField(default=timezone.now)


class RecoveryCode(Entity):
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    digest = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True)


class CredentialTicket(Entity):
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    digest = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=12, choices=[('ACTIVACION','Activación'),('RECUPERACION','Recuperación')])
    reset_mfa = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)
    credential_version = models.PositiveIntegerField()
    person_auth_version = models.PositiveIntegerField()
    issued_by = models.ForeignKey(Person, on_delete=models.PROTECT)


class Owner(Entity):
    name = models.CharField(max_length=160)
    contact = models.CharField(max_length=200)
    revision = models.PositiveIntegerField(default=1)


class OwnerLink(Entity):
    person = models.ForeignKey(Person, on_delete=models.PROTECT)
    owner = models.ForeignKey(Owner, on_delete=models.PROTECT)
    starts = models.DateTimeField(default=timezone.now)
    ends = models.DateTimeField(null=True, blank=True)
    verification_reference = models.CharField(max_length=250, blank=True)
    created_by = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='+')


class Farm(Entity):
    registry_number = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    owner = models.ForeignKey(Owner, on_delete=models.PROTECT)
    area_ha = models.DecimalField(max_digits=18, decimal_places=6)
    polygon = models.JSONField()
    country_code = models.CharField(max_length=2, default='CR')
    revision = models.PositiveIntegerField(default=1)


class FarmAssignment(Entity):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT)
    technician = models.ForeignKey(Person, on_delete=models.PROTECT)
    starts = models.DateTimeField(default=timezone.now)
    ends = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='+')
    reason = models.CharField(max_length=500, blank=True)
    revoked_by = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='+')
    revocation_reason = models.CharField(max_length=500, blank=True)


class Period(Entity):
    name = models.CharField(max_length=80)
    status = models.CharField(max_length=10, default='ABIERTA', choices=[('ABIERTA','Abierta'),('CERRADA','Cerrada')])
    created_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)


class Measurement(Entity):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name='measurements')
    period = models.ForeignKey(Period, on_delete=models.PROTECT)
    technician = models.ForeignKey(Person, on_delete=models.PROTECT)


class ReviewAssignment(Entity):
    measurement = models.ForeignKey(Measurement, on_delete=models.PROTECT)
    reviewer = models.ForeignKey(Person, on_delete=models.PROTECT)
    starts = models.DateTimeField(default=timezone.now)
    ends = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='+')
    reason = models.CharField(max_length=500, blank=True)
    revoked_by = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='+')
    revocation_reason = models.CharField(max_length=500, blank=True)


class AuditorGrant(Entity):
    auditor = models.ForeignKey(Person, on_delete=models.PROTECT)
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT)
    assignment_name = models.CharField(max_length=100)
    starts = models.DateTimeField(default=timezone.now)
    ends = models.DateTimeField()


class Version(Entity):
    measurement = models.ForeignKey(Measurement, on_delete=models.PROTECT, related_name='versions')
    number = models.PositiveIntegerField()
    author = models.ForeignKey(Person, on_delete=models.PROTECT)
    source = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True)
    amendment = models.OneToOneField('Amendment', on_delete=models.PROTECT, null=True, blank=True, related_name='correction')
    status = models.CharField(max_length=10, default='BORRADOR', choices=[(s,s.title()) for s in ('BORRADOR','ENVIADA','DEVUELTA','APROBADA')])
    measured_at = models.DateField()
    methodology = models.CharField(max_length=300)
    values = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    edit_revision = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['measurement','number'], name='one_version_number')]


class Review(Entity):
    version = models.OneToOneField(Version, on_delete=models.PROTECT, related_name='review')
    reviewer = models.ForeignKey(Person, on_delete=models.PROTECT)
    decision = models.CharField(max_length=10, choices=[('APROBADA','Aprobada'),('DEVUELTA','Devuelta')])
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class Amendment(Entity):
    source = models.ForeignKey(Version, on_delete=models.PROTECT, related_name='amendments')
    requester = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='+')
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=12, default='SOLICITADA', choices=[('SOLICITADA','Solicitada'),('AUTORIZADA','Autorizada')])
    authorizer = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='+')
    technician = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, related_name='+')
    authorized_at = models.DateTimeField(null=True, blank=True)
    authorization_reason = models.CharField(max_length=500, blank=True)


class Certificate(Entity):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT)
    review = models.OneToOneField(Review, on_delete=models.PROTECT, related_name='certificate')
    predecessor = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='replacement')
    status = models.CharField(max_length=10, default='VIGENTE', choices=[('VIGENTE','Vigente'),('INVALIDADO','Invalidado')])
    signed_bytes = models.BinaryField()
    key_id = models.CharField(max_length=71)
    created_at = models.DateTimeField(default=timezone.now)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidated_by = models.ForeignKey(Person, on_delete=models.PROTECT, null=True)
    invalidation_reason = models.CharField(max_length=500, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['farm'], condition=Q(status='VIGENTE'), name='one_current_certificate_per_farm')]


class Price(Entity):
    certificate = models.OneToOneField(Certificate, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    updated_by = models.ForeignKey(Person, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gte=0), name='nonnegative_price')]


class Event(Entity):
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(Person, on_delete=models.PROTECT, null=True)
    account_id_at_event = models.CharField(max_length=40, blank=True)
    role = models.CharField(max_length=20)
    action = models.CharField(max_length=60)
    object_id = models.CharField(max_length=64, blank=True)
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, null=True)
    measurement = models.ForeignKey(Measurement, on_delete=models.PROTECT, null=True)
    result = models.CharField(max_length=12)
    rule = models.CharField(max_length=60, blank=True)
    correlation = models.UUIDField(default=uuid.uuid4)
    detail = models.JSONField(default=dict)


class Operation(Entity):
    actor = models.ForeignKey(Person, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    action = models.CharField(max_length=40)
    digest = models.CharField(max_length=64)
    response = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor','request_id'], name='idempotency_per_person')]


class SyncReceipt(Entity):
    actor = models.ForeignKey(Person, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    version = models.ForeignKey(Version, on_delete=models.PROTECT)
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)
    base_revision = models.PositiveIntegerField()
    resulting_revision = models.PositiveIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor','request_id'], name='one_sync_receipt')]


class QueueStatus(Entity):
    """Metadatos declarados por el cliente; nunca contenido de borradores locales."""
    actor = models.ForeignKey(Person, on_delete=models.PROTECT)
    device_id = models.UUIDField()
    pending = models.PositiveIntegerField(default=0)
    conflicts = models.PositiveIntegerField(default=0)
    received_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor','device_id'], name='queue_per_person_device')]
