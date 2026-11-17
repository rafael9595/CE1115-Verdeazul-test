import json
from django.db import transaction
from . import models as m
from .policy import actor_for, require, can_read_measurement, can_report, can_download, owns, technical_scope
from .services import event


def measurement_data(measurement):
    return {'id':str(measurement.pk),'farm_id':str(measurement.farm_id),
            'farm':measurement.farm.name,'registry_number':measurement.farm.registry_number,
            'period_id':str(measurement.period_id),'period':measurement.period.name,
            'period_status':measurement.period.status,'technician_id':str(measurement.technician_id)}


def version_data(version):
    return {'id':str(version.pk),'number':version.number,'status':version.status,'edit_revision':version.edit_revision,
            'author_person_id':str(version.author_id),'source_id':str(version.source_id) if version.source_id else None,
            'measured_at':version.measured_at.isoformat(),'methodology':version.methodology,'values':version.values,
            'submitted_at':version.submitted_at.isoformat() if version.submitted_at else None}


def workspace(account_id):
    actor=actor_for(account_id)
    measurements=[]; reports=[]; versions=[]; certificates=[]; amendments=[]
    for measurement in m.Measurement.objects.select_related('farm','period').order_by('farm__name'):
        if can_report(actor,measurement): reports.append(measurement_data(measurement))
        if not can_read_measurement(actor,measurement): continue
        measurements.append(measurement_data(measurement))
        for ver in measurement.versions.order_by('number'):
            item=version_data(ver); item['measurement']=measurement_data(measurement); versions.append(item)
        for cert in m.Certificate.objects.filter(review__version__measurement=measurement).select_related('review__version__measurement__farm'):
            certificates.append({'id':str(cert.pk),'farm':measurement.farm.name,'status':cert.status,
                                 'key_id':cert.key_id,'download':can_download(actor,cert)})
        for am in m.Amendment.objects.filter(source__measurement=measurement).select_related('source'):
            amendments.append({'id':str(am.pk),'source_id':str(am.source_id),'farm':measurement.farm.name,
                               'status':am.status,'reason':am.reason,'technician_id':str(measurement.technician_id)})
    periods=[]
    for period in m.Period.objects.all().order_by('-created_at'):
        if actor.role in (m.Role.ADMIN,m.Role.MANAGER,m.Role.SUPERVISOR) or any(x['period_id']==str(period.pk) for x in measurements):
            periods.append({'id':str(period.pk),'name':period.name,'status':period.status})
    # Evento de consulta con metadatos, sin persistir el contenido técnico en logs de acceso.
    event(actor,'PANEL_CONSULTADO',detail={'measurements':len(measurements)})
    return {'role':actor.role,'person_id':str(actor.person.pk),'versions':versions,'certificates':certificates,
            'amendments':amendments,'periods':periods,'reports':reports}


def report(account_id,measurement_id,download=False):
    actor=actor_for(account_id)
    measurement=m.Measurement.objects.select_related('farm__owner','period').get(pk=measurement_id)
    require(can_report(actor,measurement),rule='C6/C5/C4')
    output={'measurement':measurement_data(measurement),'versions':[],'certificates':[],'amendments':[]}
    for ver in measurement.versions.order_by('number'):
        item=version_data(ver)
        review=m.Review.objects.filter(version=ver).first()
        if review: item['review']={'id':str(review.pk),'decision':review.decision,'reviewer_person_id':str(review.reviewer_id),
                                   'reason':review.reason,'created_at':review.created_at.isoformat()}
        output['versions'].append(item)
    for cert in m.Certificate.objects.filter(review__version__measurement=measurement).order_by('created_at'):
        item={'id':str(cert.pk),'status':cert.status,'predecessor_id':str(cert.predecessor_id) if cert.predecessor_id else None,
              'issued_at':cert.created_at.isoformat(),'key_id':cert.key_id,
              'invalidation':{'reason':cert.invalidation_reason,
                  'actor_person_id':str(cert.invalidated_by_id) if cert.invalidated_by_id else None,
                  'at':cert.invalidated_at.isoformat() if cert.invalidated_at else None},
              'signed_document':json.loads(bytes(cert.signed_bytes))}
        # O11 permite al auditor la representación firmada, nunca acceso directo O8.
        if actor.role in (m.Role.ADMIN,m.Role.MANAGER,m.Role.OWNER):
            price=m.Price.objects.filter(certificate=cert).first()
            if price: item['price']={'amount':str(price.amount),'currency':price.currency}
        output['certificates'].append(item)
    for am in m.Amendment.objects.filter(source__measurement=measurement).order_by('created_at'):
        output['amendments'].append({'id':str(am.pk),'source_id':str(am.source_id),'status':am.status,
            'reason':am.reason,'requester_person_id':str(am.requester_id),'created_at':am.created_at.isoformat(),
            'authorizer_person_id':str(am.authorizer_id) if am.authorizer_id else None,
            'technician_person_id':str(am.technician_id) if am.technician_id else None,
            'authorization_reason':am.authorization_reason,
            'authorized_at':am.authorized_at.isoformat() if am.authorized_at else None})
    if actor.role in (m.Role.ADMIN,m.Role.OWNER):
        output['owner']={'name':measurement.farm.owner.name,'contact':measurement.farm.owner.contact}
    event(actor,'REPORTE_DESCARGADO' if download else 'REPORTE_CONSULTADO',measurement.pk,measurement=measurement)
    return output


def download_certificate(account_id,certificate_id):
    actor=actor_for(account_id)
    cert=m.Certificate.objects.select_related('farm','review__version__measurement__farm').get(pk=certificate_id)
    require(can_download(actor,cert),rule='O8')
    event(actor,'CERTIFICADO_DESCARGADO',cert.pk,measurement=cert.review.version.measurement)
    return bytes(cert.signed_bytes)


def read_price(account_id,certificate_id):
    actor=actor_for(account_id)
    cert=m.Certificate.objects.select_related('farm','review__version__measurement').get(pk=certificate_id)
    require(actor.role in (m.Role.ADMIN,m.Role.MANAGER) or (actor.role==m.Role.OWNER and owns(actor.person,cert.farm)),rule='O10')
    price=m.Price.objects.filter(certificate=cert).first()
    event(actor,'PRECIO_CONSULTADO',cert.pk,measurement=cert.review.version.measurement)
    return {'amount':str(price.amount),'currency':price.currency} if price else {'amount':None,'currency':None}


def audit(account_id,download=False):
    actor=actor_for(account_id)
    require(actor.role in (m.Role.ADMIN,m.Role.SECURITY,m.Role.MANAGER,m.Role.SUPERVISOR,m.Role.TECH,m.Role.REVIEWER),rule='O12')
    if download: require(actor.role in (m.Role.ADMIN,m.Role.SECURITY),rule='O12-D')
    rows=[]
    for row in m.Event.objects.select_related('measurement__farm').order_by('-created_at')[:1000]:
        allowed=actor.role in (m.Role.ADMIN,m.Role.SECURITY)
        if actor.role==m.Role.MANAGER: allowed=row.action.startswith(('CERTIFICADO_','REVISION_'))
        if actor.role==m.Role.SUPERVISOR: allowed=row.measurement_id is not None and not row.action.startswith('PRECIO_')
        if actor.role in (m.Role.TECH,m.Role.REVIEWER):
            allowed=row.measurement_id is not None and technical_scope(actor,row.measurement) and not row.action.startswith('PRECIO_')
        if allowed:
            item={'id':str(row.pk),'date':row.created_at.isoformat(),'actor_id':str(row.actor_id),
                  'role':row.role,'action':row.action,'object_id':row.object_id,'result':row.result,'rule':row.rule}
            if actor.role==m.Role.ADMIN: item['detail']=row.detail
            rows.append(item)
    event(actor,'BITACORA_DESCARGADA' if download else 'BITACORA_CONSULTADA')
    return rows
