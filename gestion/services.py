"""Única entrada de mutación del módulo. Autorización, bloqueos y firma atómicos."""
import hashlib
import json
import uuid
from datetime import date, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from certificados import issue_certificate, certificate_bytes, load_private_key_from_environment, CertificateError
from . import models as m
from .policy import (Actor, DomainError, require, actor_for, assigned_tech, assigned_reviewer,
                     can_read_measurement, technical_scope, owns)
from .geo import validate_geography
from .validation import measurement_data as validate_measurement, expected_revision

MUTATIONS = {'approve','return','request_amendment','authorize_amendment','invalidate','set_price',
             'correct','edit','submit','open_period','close_period'}


def event(actor, action, target='', result='OK', rule='', measurement=None, detail=None, correlation=None):
    return m.Event.objects.create(actor=actor.person, account_id_at_event=str(actor.account.pk), role=actor.role,
        action=action, object_id=str(target), result=result, rule=rule,
        farm=measurement.farm if measurement else None, measurement=measurement, detail=detail or {},
        **({'correlation':correlation} if correlation else {}))


def reason(data, field='reason'):
    value=data.get(field)
    require(isinstance(value,str) and 1 <= len(value.strip()) <= 500,
            'Se requiere un motivo de 1 a 500 caracteres.', 'MOTIVO', 400)
    return value.strip()


def _keys(data, allowed, required=()):
    require(isinstance(data,dict) and set(data)<=set(allowed) and set(required)<=set(data),
            'Campos faltantes o no permitidos.', 'CAMPOS', 400)


def _utc(dt): return dt.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def snapshot(version, review, cert_id, created, predecessor):
    measurement=version.measurement; farm=measurement.farm
    return {'certificate_id':str(cert_id), 'issuer':'Verdeazul Carbono S.A.', 'issued_at':_utc(created),
      'farm':{'id':str(farm.pk),'registry_number':farm.registry_number,'name':farm.name,
              'area_ha':format(farm.area_ha,'f'),'country_code':farm.country_code,'polygon_wgs84':farm.polygon},
      'measurement':{'id':str(measurement.pk),'version_id':str(version.pk),'period_id':str(measurement.period_id),
                     'measured_at':version.measured_at.isoformat(),'methodology':version.methodology,'values':version.values},
      'approval':{'id':str(review.pk),'verifier_person_id':str(review.reviewer_id),'decided_at':_utc(review.created_at)},
      'technical_participants':sorted({str(p) for p in measurement.versions.values_list('author_id',flat=True)}),
      'predecessor_certificate_id':str(predecessor.pk) if predecessor else None}


def _resolve(action, target):
    """Orden global: persona -> período -> finca -> medición -> versión -> objeto."""
    try:
        if action in ('invalidate','set_price'):
            obj=m.Certificate.objects.select_related('review__version').get(pk=target)
            ver=obj.review.version
        elif action=='authorize_amendment':
            obj=m.Amendment.objects.select_related('source').get(pk=target); ver=obj.source
        else:
            ver=m.Version.objects.get(pk=target); obj=ver
        measurement=m.Measurement.objects.get(pk=ver.measurement_id)
        period=m.Period.objects.select_for_update().get(pk=measurement.period_id)
        farm=m.Farm.objects.select_for_update().get(pk=measurement.farm_id)
        measurement=m.Measurement.objects.select_for_update().get(pk=measurement.pk)
        measurement.farm=farm; measurement.period=period
        ver=m.Version.objects.select_for_update().get(pk=ver.pk); ver.measurement=measurement
        if action in ('invalidate','set_price'):
            obj=m.Certificate.objects.select_for_update().get(pk=obj.pk)
        elif action=='authorize_amendment':
            obj=m.Amendment.objects.select_for_update().get(pk=obj.pk)
        else: obj=ver
        return obj,ver,measurement
    except (m.Version.DoesNotExist,m.Measurement.DoesNotExist,m.Certificate.DoesNotExist,m.Amendment.DoesNotExist,
            m.Farm.DoesNotExist,m.Period.DoesNotExist,ValueError,ValidationError):
        raise DomainError('Objeto no disponible.', 'OBJETO', 404)


def _authorize(actor, action, ver, obj, measurement):
    if action in ('approve','return'):
        require(actor.role==m.Role.REVIEWER, rule='O6')
        require(assigned_reviewer(actor.person,measurement), rule='C3')
        require(not measurement.versions.filter(author=actor.person).exists(),
                'No puede revisar una cadena en la que participó como autor o corrector.', 'C3')
    elif action=='request_amendment':
        require(actor.role in (m.Role.ADMIN,m.Role.MANAGER,m.Role.SUPERVISOR,m.Role.TECH,m.Role.REVIEWER,m.Role.OWNER)
                and can_read_measurement(actor,measurement),rule='O7')
    elif action in ('authorize_amendment','invalidate'):
        require(actor.role==m.Role.ADMIN,rule='C7' if action=='authorize_amendment' else 'C8')
        actor.recent()
    elif action=='set_price':
        require(actor.role in (m.Role.ADMIN,m.Role.MANAGER),rule='O10')
    elif action in ('correct','edit','submit'):
        require(actor.role==m.Role.TECH and measurement.technician_id==actor.person.pk
                and ver.author_id==actor.person.pk and assigned_tech(actor.person,measurement.farm),rule='C2')


def _allow_correction(ver, measurement, data):
    """Se conserva cada versión enviada: una corrección crea una versión nueva."""
    require(ver.status in ('DEVUELTA','APROBADA'), 'Solo se corrige una versión devuelta o aprobada.', 'C2',409)
    require(not measurement.versions.filter(status__in=['BORRADOR','ENVIADA']).exists(),
            'Ya existe una versión pendiente para esta medición.', 'C2',409)
    require(not measurement.versions.filter(number__gt=ver.number).exists(),
            'La corrección debe partir de la última versión.', 'VERSION',409)
    amendment=None
    if data.get('amendment_id'):
        try: amendment=m.Amendment.objects.select_for_update().get(pk=data['amendment_id'])
        except (m.Amendment.DoesNotExist,ValueError,ValidationError): raise DomainError('Enmienda no disponible.','C7',400)
        require(amendment.source_id==ver.pk and amendment.status=='AUTORIZADA' and
                amendment.technician_id==measurement.technician_id and not hasattr(amendment,'correction'),rule='C7')
    if measurement.period.status=='CERRADA' or ver.status=='APROBADA':
        require(amendment is not None, 'Se requiere una enmienda autorizada para esta versión y técnico.', 'C7')
    return amendment


def _period_editable(ver, measurement):
    if measurement.period.status=='ABIERTA': return
    amendment=ver.amendment
    require(amendment is not None and amendment.status=='AUTORIZADA' and
            amendment.technician_id==ver.author_id and amendment.source.measurement_id==measurement.pk,
            'El período está cerrado; se requiere una corrección autorizada.', 'C2')


def _mutate(actor, action, obj, ver, measurement, data):
    if action in ('approve','return'):
        _keys(data, [] if action=='approve' else ['reason'])
        require(ver.status=='ENVIADA' and not m.Review.objects.filter(version=ver).exists(),
                'La versión no está disponible para revisión.', 'C3',409)
        decision='APROBADA' if action=='approve' else 'DEVUELTA'
        why=reason(data) if action=='return' else ''
        predecessor=None
        if action=='approve':
            validate_geography(measurement.farm)
            require(not m.Certificate.objects.filter(farm=measurement.farm,status='VIGENTE').exists(),
                    'Ya existe un certificado vigente para esta finca.', 'C9',409)
            previous=m.Certificate.objects.filter(farm=measurement.farm).order_by('-created_at').first()
            if previous:
                require(ver.amendment_id is not None and ver.amendment.status=='AUTORIZADA' and
                        ver.amendment.source_id==previous.review.version_id and
                        ver.amendment.technician_id==ver.author_id and previous.status=='INVALIDADO',
                        'El reemplazo requiere enmienda y antecedente invalidado.', 'C9',409)
                predecessor=previous
        review=m.Review.objects.create(version=ver,reviewer=actor.person,decision=decision,reason=why)
        ver.status=decision; ver.save(update_fields=['status'])
        event(actor,'REVISION_'+decision,review.pk,measurement=measurement,detail={'version_id':str(ver.pk)})
        if action=='return': return {'review_id':str(review.pk),'version_id':str(ver.pk),'status':decision}
        created=timezone.now(); cert_id=uuid.uuid4()
        document=issue_certificate(snapshot(ver,review,cert_id,created,predecessor),load_private_key_from_environment())
        cert=m.Certificate.objects.create(id=cert_id,farm=measurement.farm,review=review,predecessor=predecessor,
            signed_bytes=certificate_bytes(document),key_id=document['key_id'],created_at=created)
        event(actor,'CERTIFICADO_EMITIDO',cert.pk,measurement=measurement,
              detail={'service':'emision','review_id':str(review.pk),'key_id':cert.key_id})
        return {'review_id':str(review.pk),'certificate_id':str(cert.pk),'status':'VIGENTE'}
    if action=='request_amendment':
        _keys(data,['reason'],['reason'])
        require(ver.status in ('APROBADA','DEVUELTA'), 'La versión debe estar aprobada o devuelta.', 'C7',409)
        require(not m.Amendment.objects.filter(source=ver,status='SOLICITADA').exists(),
                'Ya hay una solicitud pendiente para esta versión.', 'C7',409)
        am=m.Amendment.objects.create(source=ver,requester=actor.person,reason=reason(data))
        event(actor,'ENMIENDA_SOLICITADA',am.pk,measurement=measurement)
        return {'amendment_id':str(am.pk),'status':am.status}
    if action=='authorize_amendment':
        _keys(data,['reason','technician_id'],['reason','technician_id'])
        require(obj.status=='SOLICITADA','La solicitud ya fue tramitada.','C7',409)
        require(data['technician_id']==str(measurement.technician_id) and
                m.Role.TECH in measurement.technician.direct_roles and measurement.technician.accounts.filter(is_active=True).exists(),
                'La corrección corresponde al técnico original disponible.', 'C7')
        require(assigned_tech(measurement.technician,measurement.farm), 'El técnico debe tener asignación vigente.','C7')
        require(not m.Amendment.objects.filter(source=ver,status='AUTORIZADA',correction__isnull=True).exists(),
                'Ya existe una autorización pendiente de utilizar.','C7',409)
        obj.status='AUTORIZADA'; obj.authorizer=actor.person; obj.technician=measurement.technician
        obj.authorized_at=timezone.now(); obj.authorization_reason=reason(data); obj.save()
        event(actor,'ENMIENDA_AUTORIZADA',obj.pk,measurement=measurement)
        return {'amendment_id':str(obj.pk),'status':obj.status}
    if action=='correct':
        _keys(data,['amendment_id'])
        am=_allow_correction(ver,measurement,data)
        corrected=m.Version.objects.create(measurement=measurement,number=ver.number+1,author=actor.person,
            source=ver,amendment=am,measured_at=ver.measured_at,methodology=ver.methodology,values=ver.values)
        event(actor,'CORRECCION_CREADA',corrected.pk,measurement=measurement,detail={'source_id':str(ver.pk)})
        return {'version_id':str(corrected.pk),'status':'BORRADOR'}
    if action in ('edit','submit'):
        require(ver.status=='BORRADOR','Solo se modifica o envía una versión en borrador.','C2',409)
        _period_editable(ver,measurement)
        if action=='edit':
            _keys(data,['values','methodology','measured_at','expected_revision'],['values','methodology','measured_at','expected_revision'])
            expected_revision(data['expected_revision'],ver.edit_revision)
            cleaned=validate_measurement(data)
            before={'values':ver.values,'methodology':ver.methodology,'measured_at':ver.measured_at.isoformat()}
            ver.values=cleaned['values']; ver.methodology=cleaned['methodology']; ver.measured_at=cleaned['measured_at']
            ver.edit_revision+=1
            ver.save(update_fields=['values','methodology','measured_at','edit_revision'])
            event(actor,'BORRADOR_EDITADO',ver.pk,measurement=measurement,detail={'before':before,'after':data})
        else:
            _keys(data,['expected_revision'],['expected_revision'])
            expected_revision(data['expected_revision'],ver.edit_revision)
            validate_measurement({'measured_at':ver.measured_at.isoformat(),'methodology':ver.methodology,'values':ver.values})
            ver.status='ENVIADA'; ver.submitted_at=timezone.now(); ver.edit_revision+=1
            ver.save(update_fields=['status','submitted_at','edit_revision'])
            event(actor,'MEDICION_ENVIADA',ver.pk,measurement=measurement)
        return {'version_id':str(ver.pk),'status':ver.status,'edit_revision':ver.edit_revision}
    if action=='invalidate':
        _keys(data,['reason'],['reason'])
        require(obj.status=='VIGENTE','El certificado ya no está vigente.','C8',409)
        obj.status='INVALIDADO'; obj.invalidated_by=actor.person; obj.invalidated_at=timezone.now()
        obj.invalidation_reason=reason(data)
        obj.save(update_fields=['status','invalidated_by','invalidated_at','invalidation_reason'])
        event(actor,'CERTIFICADO_INVALIDADO',obj.pk,measurement=measurement)
        return {'certificate_id':str(obj.pk),'status':'INVALIDADO'}
    if action=='set_price':
        _keys(data,['amount','currency'],['amount','currency'])
        try: amount=Decimal(data['amount'])
        except (InvalidOperation,TypeError,ValueError): raise DomainError('Monto inválido.','O10',400)
        require(isinstance(data['amount'],str) and amount.is_finite() and 0<=amount<Decimal('10000000000000000')
                and amount==amount.quantize(Decimal('0.01')) and data['currency'] in ('CRC','USD','EUR'),
                'Monto o moneda inválidos.','O10',400)
        m.Price.objects.update_or_create(certificate=obj,defaults={'amount':amount,'currency':data['currency'],
                                                               'updated_by':actor.person,'updated_at':timezone.now()})
        event(actor,'PRECIO_REGISTRADO',obj.pk,measurement=measurement)
        return {'certificate_id':str(obj.pk),'amount':format(amount,'.2f'),'currency':data['currency']}
    raise DomainError('Operación no implementada.','OPERACION',400)


def execute(account_id, action, target, data, request_id, authenticated_at=None):
    """authenticated_at proviene de sesión servidor; nunca de datos del cliente."""
    actor=actor_for(account_id,authenticated_at)
    try:
        require(action in MUTATIONS,'Operación desconocida.','OPERACION',400)
        try: operation_id=uuid.UUID(str(request_id))
        except (ValueError,TypeError): raise DomainError('Se requiere UUID de operación.','IDEMPOTENCIA',400)
        digest=hashlib.sha256(json.dumps({'action':action,'target':str(target),'data':data},
                            sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        with transaction.atomic():
            m.Person.objects.select_for_update().get(pk=actor.person.pk)
            actor=actor_for(account_id,authenticated_at,lock=True)
            measurement=None
            if action in ('open_period','close_period'):
                require(actor.role in (m.Role.ADMIN,m.Role.MANAGER),rule='O4')
                obj=None
                if action=='close_period':
                    try: obj=m.Period.objects.select_for_update().get(pk=target)
                    except (m.Period.DoesNotExist,ValueError,ValidationError): raise DomainError('Período no disponible.','O4',404)
            else:
                obj,ver,measurement=_resolve(action,target)
                _authorize(actor,action,ver,obj,measurement)
            prior=m.Operation.objects.filter(actor=actor.person,request_id=operation_id).first()
            if prior:
                require(prior.digest==digest, 'El UUID de operación ya se utilizó con otro contenido.', 'IDEMPOTENCIA',409)
                return prior.response
            if action=='open_period':
                _keys(data,['name'],['name'])
                require(isinstance(data['name'],str) and 1<=len(data['name'].strip())<=80,'Nombre inválido.','O4',400)
                obj=m.Period.objects.create(name=data['name'].strip())
                event(actor,'PERIODO_ABIERTO',obj.pk)
                response={'period_id':str(obj.pk),'status':obj.status}
            elif action=='close_period':
                _keys(data,['reason'],['reason']); why=reason(data)
                require(obj.status=='ABIERTA','El período ya está cerrado.','O4',409)
                obj.status='CERRADA'; obj.closed_at=timezone.now(); obj.save(update_fields=['status','closed_at'])
                event(actor,'PERIODO_CERRADO',obj.pk,detail={'reason':why})
                response={'period_id':str(obj.pk),'status':obj.status}
            else:
                response=_mutate(actor,action,obj,ver,measurement,data)
            m.Operation.objects.create(actor=actor.person,request_id=operation_id,action=action,digest=digest,response=response)
            return response
    except (DomainError,CertificateError,IntegrityError) as exc:
        error=exc if isinstance(exc,DomainError) else DomainError(
            'La operación no se confirmó; revise datos, clave de firma o conflicto de registros.',
            'FIRMA' if isinstance(exc,CertificateError) else 'INTEGRIDAD',409)
        # Fuera de la transacción revertida: guardar la denegación sin conservar cambios parciales.
        event(actor,action,str(target),result='DENEGADO',rule=error.rule)
        raise error from exc
