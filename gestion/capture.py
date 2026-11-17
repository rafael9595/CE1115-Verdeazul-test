from .policy import role_filter
"""Catálogo, asignaciones, captura y recepción idempotente de borradores."""
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from . import models as m
from .policy import (actor_for, require, DomainError, live, assigned_tech, assigned_reviewer,
                     owns, participated, can_read_measurement)
from .services import event, _keys, reason, _resolve, _authorize, _period_editable
from .validation import text, measurement_data, expected_revision, DECIMAL
from .geo import validate_geography

ACTIONS={'create_owner','edit_owner','link_owner','revoke_owner_link','create_farm','edit_farm',
         'assign_tech','assign_reviewer','revoke_tech','revoke_reviewer','create_measurement','sync','queue_status'}
MANAGERS=(m.Role.ADMIN,m.Role.SUPERVISOR)


def can_read_farm(actor,farm):
    if actor.role in (m.Role.ADMIN,m.Role.MANAGER,m.Role.SUPERVISOR): return True
    if actor.role==m.Role.OWNER: return owns(actor.person,farm)
    if actor.role==m.Role.TECH and assigned_tech(actor.person,farm): return True
    if actor.role==m.Role.REVIEWER and live(m.ReviewAssignment.objects.filter(reviewer=actor.person,measurement__farm=farm)).exists(): return True
    if actor.role in (m.Role.TECH,m.Role.REVIEWER):
        return (m.Version.objects.filter(measurement__farm=farm,author=actor.person).exists() or
                m.Review.objects.filter(version__measurement__farm=farm,reviewer=actor.person).exists())
    return False


def farm_data(actor,farm):
    out={'id':str(farm.pk),'registry_number':farm.registry_number,'name':farm.name,
         'area_ha':str(farm.area_ha),'country_code':farm.country_code,'polygon':farm.polygon,'revision':farm.revision}
    if actor.role in (m.Role.ADMIN,m.Role.OWNER):
        out['owner_id']=str(farm.owner_id); out['owner_name']=farm.owner.name
    return out


def catalog(account_id,farm_id=None):
    actor=actor_for(account_id)
    require(actor.role not in (m.Role.AUDITOR,m.Role.SECURITY),rule='O2')
    qs=m.Farm.objects.select_related('owner').order_by('name')
    if farm_id:
        farm=qs.get(pk=farm_id); require(can_read_farm(actor,farm),rule='C5/C4'); farms=[farm]
    else: farms=[f for f in qs if can_read_farm(actor,f)]
    output={'role':actor.role,'farms':[farm_data(actor,f) for f in farms]}
    event(actor,'CATALOGO_CONSULTADO',farm_id or '',detail={'count':len(farms)})
    return output


def owners(account_id):
    actor=actor_for(account_id); require(actor.role in (m.Role.ADMIN,m.Role.OWNER),rule='O9')
    qs=m.Owner.objects.all().order_by('name')
    if actor.role==m.Role.OWNER: qs=qs.filter(pk__in=live(m.OwnerLink.objects.filter(person=actor.person)).values('owner_id'))
    output={'role':actor.role,'owners':[{'id':str(o.pk),'name':o.name,'contact':o.contact,'revision':o.revision} for o in qs]}
    if actor.role==m.Role.ADMIN:
        output['people']=[{'id':str(p.pk),'work_id':p.work_id} for p in m.Person.objects.filter(role_filter(m.Role.OWNER),accounts__is_active=True).distinct()]
        output['links']=[{'id':str(x.pk),'owner_id':str(x.owner_id),'person_id':str(x.person_id),
                         'work_id':x.person.work_id,'active':live(m.OwnerLink.objects.filter(pk=x.pk)).exists(),
                         'reference':x.verification_reference} for x in m.OwnerLink.objects.select_related('person')]
    event(actor,'PROPIETARIOS_CONSULTADOS',detail={'count':len(output['owners'])})
    return output


def assignments(account_id):
    actor=actor_for(account_id)
    require(actor.role in (*MANAGERS,m.Role.MANAGER,m.Role.SECURITY,m.Role.TECH,m.Role.REVIEWER),rule='O3')
    rows=[]
    for model,field,kind in ((m.FarmAssignment,'technician','tecnico'),(m.ReviewAssignment,'reviewer','verificador')):
        qs=model.objects.select_related(field).order_by('-starts')
        if actor.role in (m.Role.TECH,m.Role.REVIEWER): qs=qs.filter(**{field:actor.person})
        for x in qs:
            person=getattr(x,field)
            rows.append({'id':str(x.pk),'kind':kind,'person_id':str(person.pk),'work_id':person.work_id,
                'farm_id':str(x.farm_id) if kind=='tecnico' else str(x.measurement.farm_id),
                'measurement_id':str(x.measurement_id) if kind=='verificador' else None,
                'starts':x.starts.isoformat(),'ends':x.ends.isoformat() if x.ends else None,
                'active':live(model.objects.filter(pk=x.pk)).exists()})
    out={'role':actor.role,'assignments':rows}
    if actor.role in MANAGERS:
        out['technicians']=[{'id':str(x.pk),'work_id':x.work_id} for x in m.Person.objects.filter(role_filter(m.Role.TECH),accounts__is_active=True).distinct()]
        out['reviewers']=[{'id':str(x.pk),'work_id':x.work_id} for x in m.Person.objects.filter(role_filter(m.Role.REVIEWER),accounts__is_active=True).distinct()]
        out['farms']=[{'id':str(f.pk),'name':f.name,'registry_number':f.registry_number} for f in m.Farm.objects.all()]
        out['measurements']=[{'id':str(x.pk),'farm':x.farm.name,'period':x.period.name,'technician':x.technician.work_id}
                             for x in m.Measurement.objects.select_related('farm','period','technician')]
    event(actor,'ASIGNACIONES_CONSULTADAS')
    return out


def bootstrap(account_id):
    from .queries import version_data,measurement_data as brief
    actor=actor_for(account_id); require(actor.role==m.Role.TECH,rule='C2/C11')
    farms=[f for f in m.Farm.objects.all() if assigned_tech(actor.person,f)]
    versions=[]
    for v in m.Version.objects.filter(author=actor.person,status='BORRADOR',measurement__technician=actor.person).select_related('measurement__farm','measurement__period'):
        if not assigned_tech(actor.person,v.measurement.farm): continue
        try: _period_editable(v,v.measurement)
        except DomainError: continue
        versions.append({**version_data(v),'measurement':brief(v.measurement)})
    periods={str(p.pk):{'id':str(p.pk),'name':p.name,'status':p.status} for p in m.Period.objects.filter(status='ABIERTA')}
    for v in versions:
        info=v['measurement']; periods[info['period_id']]={'id':info['period_id'],'name':info['period'],'status':info['period_status']}
    event(actor,'CAPTURA_PREPARADA',detail={'farms':len(farms),'drafts':len(versions)})
    return {'person_id':str(actor.person.pk),'username':actor.account.username,'role':actor.role,
            'farms':[{'id':str(f.pk),'name':f.name,'registry_number':f.registry_number} for f in farms],
            'periods':list(periods.values()),'versions':versions,'server_time':timezone.now().isoformat()}


def queue_status(account_id):
    actor=actor_for(account_id); require(actor.role in (*MANAGERS,m.Role.TECH),rule='O16')
    qs=m.QueueStatus.objects.select_related('actor').order_by('-received_at')
    if actor.role==m.Role.TECH: qs=qs.filter(actor=actor.person)
    event(actor,'ESTADO_COLAS_CONSULTADO')
    return {'role':actor.role,'queues':[{'person_id':str(x.actor_id),'work_id':x.actor.work_id,'device_id':str(x.device_id),
            'pending':x.pending,'conflicts':x.conflicts,'received_at':x.received_at.isoformat()} for x in qs]}


def _context(actor,action,target,data):
    """Autoriza antes de devolver resultados idempotentes y antes de mutar."""
    if action in ('create_owner','link_owner','revoke_owner_link','create_farm','edit_farm'):
        require(actor.role==m.Role.ADMIN,rule='O9' if 'owner' in action else 'O2')
    if action=='edit_owner': require(actor.role in (m.Role.ADMIN,m.Role.OWNER),rule='O9')
    if action.startswith(('assign_','revoke_')) and 'owner' not in action: require(actor.role in MANAGERS,rule='O3')
    if action in ('create_measurement','sync','queue_status'): require(actor.role==m.Role.TECH,rule='C2/C11')
    if action in ('edit_owner','link_owner'):
        obj=m.Owner.objects.select_for_update().get(pk=target)
        if actor.role==m.Role.OWNER:
            require(live(m.OwnerLink.objects.filter(person=actor.person,owner=obj)).exists(),rule='C4')
        return {'obj':obj}
    if action=='revoke_owner_link':
        obj=m.OwnerLink.objects.select_for_update().get(pk=target); return {'obj':obj}
    if action in ('edit_farm','assign_tech'):
        return {'obj':m.Farm.objects.select_for_update().get(pk=target)}
    if action in ('assign_reviewer','revoke_reviewer'):
        link=m.ReviewAssignment.objects.get(pk=target) if action=='revoke_reviewer' else None
        mid=link.measurement_id if link else target
        meas=m.Measurement.objects.get(pk=mid)
        m.Period.objects.select_for_update().get(pk=meas.period_id)
        m.Farm.objects.select_for_update().get(pk=meas.farm_id)
        meas=m.Measurement.objects.select_for_update().get(pk=mid)
        return {'obj':m.ReviewAssignment.objects.select_for_update().get(pk=target) if link else meas}
    if action=='revoke_tech':
        link=m.FarmAssignment.objects.get(pk=target)
        m.Farm.objects.select_for_update().get(pk=link.farm_id)
        return {'obj':m.FarmAssignment.objects.select_for_update().get(pk=target)}
    if action in ('create_measurement','sync'):
        if action=='sync':
            require(data.get('author_person_id')==str(actor.person.pk),'El borrador pertenece a otra persona.','C11',403)
        if action=='sync' and data.get('version_id'):
            _,ver,meas=_resolve('edit',data['version_id']); _authorize(actor,'edit',ver,ver,meas)
            require(str(meas.farm_id)==data.get('farm_id') and str(meas.period_id)==data.get('period_id'),
                    'La versión no corresponde a la finca/período indicados.','C11',409)
            return {'ver':ver,'measurement':meas,'farm':meas.farm,'period':meas.period}
        period=m.Period.objects.select_for_update().get(pk=data.get('period_id'))
        farm=m.Farm.objects.select_for_update().get(pk=data.get('farm_id'))
        require(assigned_tech(actor.person,farm),rule='C2')
        return {'farm':farm,'period':period}
    return {}


def _mutate(actor,action,data,ctx,operation_id):
    obj=ctx.get('obj'); now=timezone.now()
    if action=='create_owner':
        _keys(data,['name','contact'],['name','contact'])
        obj=m.Owner.objects.create(name=text(data['name'],1,160,'Nombre legal'),contact=text(data['contact'],1,200,'Contacto'))
        event(actor,'PROPIETARIO_CREADO',obj.pk)
        return {'owner_id':str(obj.pk),'revision':obj.revision}
    if action=='edit_owner':
        allowed=['contact','expected_revision']+(['name'] if actor.role==m.Role.ADMIN else [])
        _keys(data,allowed,['contact','expected_revision']); expected_revision(data['expected_revision'],obj.revision)
        obj.contact=text(data['contact'],1,200,'Contacto')
        if 'name' in data: obj.name=text(data['name'],1,160,'Nombre legal')
        obj.revision+=1; obj.save()
        event(actor,'PROPIETARIO_ACTUALIZADO',obj.pk,detail={'revision':obj.revision,'fields':sorted(set(data)-{'expected_revision'})})
        return {'owner_id':str(obj.pk),'revision':obj.revision}
    if action=='link_owner':
        _keys(data,['person_id','verification_reference'],['person_id','verification_reference'])
        person=m.Person.objects.get(pk=data['person_id'])
        require(m.Role.OWNER in person.direct_roles and person.accounts.filter(is_active=True).exists(),rule='C4')
        require(not live(m.OwnerLink.objects.filter(person=person,owner=obj)).exists(),'El vínculo ya está vigente.','C4',409)
        link=m.OwnerLink.objects.create(person=person,owner=obj,created_by=actor.person,
                   verification_reference=text(data['verification_reference'],1,250,'Referencia de verificación'))
        event(actor,'VINCULO_PROPIETARIO_CREADO',link.pk,detail={'owner_id':str(obj.pk),'person_id':str(person.pk)})
        return {'link_id':str(link.pk)}
    if action=='revoke_owner_link':
        _keys(data,['reason'],['reason']); why=reason(data)
        require(live(m.OwnerLink.objects.filter(pk=obj.pk)).exists(),'El vínculo no está vigente.','C4',409)
        obj.ends=now; obj.save(update_fields=['ends'])
        event(actor,'VINCULO_PROPIETARIO_REVOCADO',obj.pk,detail={'reason':why})
        return {'link_id':str(obj.pk),'status':'FINALIZADO'}
    if action in ('create_farm','edit_farm'):
        fields=['registry_number','name','owner_id','area_ha','polygon']
        if action=='edit_farm': fields+=['expected_revision','reason']
        _keys(data,fields,fields)
        if obj: expected_revision(data['expected_revision'],obj.revision)
        owner=m.Owner.objects.get(pk=data['owner_id'])
        require(isinstance(data['area_ha'],str),'El área debe ser un decimal.','CAMPOS',400)
        try:
            area=Decimal(data['area_ha'])
            require(area.is_finite() and 0<area<Decimal('1000000000000') and area==area.quantize(Decimal('.000001')),
                    'Área positiva con hasta seis decimales.','CAMPOS',400)
        except InvalidOperation: raise DomainError('Área inválida.','CAMPOS',400)
        if not obj: obj=m.Farm(owner=owner)
        before={'revision':obj.revision,'owner_id':str(obj.owner_id)} if obj.pk and action=='edit_farm' else None
        obj.registry_number=text(data['registry_number'],1,80,'Número registral')
        obj.name=text(data['name'],1,160,'Nombre de finca'); obj.owner=owner; obj.area_ha=area; obj.polygon=data['polygon']
        # Coordenadas como decimales en texto para el mismo contrato de firma.
        require(isinstance(obj.polygon,list) and all(isinstance(p,list) and len(p)==2 and
                all(isinstance(v,str) and DECIMAL.fullmatch(v) for v in p) for p in obj.polygon),'Use pares de coordenadas en texto.','CAMPOS',400)
        validate_geography(obj)
        if action=='edit_farm': obj.revision+=1
        obj.save()
        event(actor,'FINCA_CREADA' if action=='create_farm' else 'FINCA_ACTUALIZADA',obj.pk,
              detail={'revision':obj.revision,'before':before,'reason':reason(data) if action=='edit_farm' else ''})
        return {'farm_id':str(obj.pk),'revision':obj.revision}
    if action in ('assign_tech','assign_reviewer'):
        _keys(data,['person_id','reason'],['person_id','reason']); why=reason(data)
        person=m.Person.objects.get(pk=data['person_id']); role=m.Role.TECH if action=='assign_tech' else m.Role.REVIEWER
        require(role in person.direct_roles and person.accounts.filter(is_active=True).exists(),'La persona no tiene el rol requerido activo.','O3',403)
        model=m.FarmAssignment if role==m.Role.TECH else m.ReviewAssignment
        fields={'farm':obj,'technician':person} if role==m.Role.TECH else {'measurement':obj,'reviewer':person}
        if role==m.Role.REVIEWER:
            require(not obj.versions.filter(author=person).exists(),'El autor/corrector no puede revisar esta cadena.','C3',403)
        require(not live(model.objects.filter(**fields)).exists(),'La asignación ya está vigente.','O3',409)
        link=model.objects.create(**fields,created_by=actor.person,reason=why)
        event(actor,'ASIGNACION_CREADA',link.pk,measurement=obj if role==m.Role.REVIEWER else None,
              detail={'person_id':str(person.pk),'target':str(obj.pk),'function':role})
        return {'assignment_id':str(link.pk)}
    if action in ('revoke_tech','revoke_reviewer'):
        _keys(data,['reason'],['reason']); why=reason(data)
        require(obj.starts<=now and (obj.ends is None or obj.ends>now),'La asignación no está vigente.','O3',409)
        obj.ends=now; obj.revoked_by=actor.person; obj.revocation_reason=why; obj.save(update_fields=['ends','revoked_by','revocation_reason'])
        event(actor,'ASIGNACION_REVOCADA',obj.pk,detail={'reason':why,'function':action})
        return {'assignment_id':str(obj.pk),'status':'FINALIZADA'}
    if action in ('create_measurement','sync'):
        fields=['farm_id','period_id','measured_at','methodology','values']
        if action=='sync': fields+=['author_person_id','version_id','base_revision','captured_at']
        _keys(data,fields,fields)
        cleaned=measurement_data(data); ver=ctx.get('ver'); meas=ctx.get('measurement')
        if ver:
            require(ver.status=='BORRADOR','El servidor ya recibió o resolvió esta versión. Se conserva el pendiente local.','C11',409)
            _period_editable(ver,meas); expected_revision(data['base_revision'],ver.edit_revision)
            before={'revision':ver.edit_revision,'values':ver.values,'methodology':ver.methodology,'measured_at':ver.measured_at.isoformat()}
            for k,v in cleaned.items(): setattr(ver,k,v)
            ver.edit_revision+=1; ver.save(update_fields=['values','methodology','measured_at','edit_revision'])
        else:
            require(ctx['period'].status=='ABIERTA','El período está cerrado. Se conserva el pendiente local.','C2',409)
            if action=='sync':
                require(data['version_id'] is None and type(data['base_revision']) is int and data['base_revision']==0,
                        'Una medición nueva necesita versión nula y revisión base 0.','C11',400)
            meas=m.Measurement.objects.create(farm=ctx['farm'],period=ctx['period'],technician=actor.person)
            ver=m.Version.objects.create(measurement=meas,number=1,author=actor.person,**cleaned)
            before=None
        response={'measurement_id':str(meas.pk),'version_id':str(ver.pk),'status':ver.status,'edit_revision':ver.edit_revision}
        if action=='sync':
            captured=parse_datetime(data['captured_at']) if isinstance(data['captured_at'],str) else None
            require(captured is not None and timezone.is_aware(captured),'La fecha de captura debe incluir zona horaria.','C11',400)
            receipt=m.SyncReceipt.objects.create(actor=actor.person,request_id=operation_id,version=ver,captured_at=captured,
                                                base_revision=data['base_revision'],resulting_revision=ver.edit_revision)
            response.update({'receipt_id':str(receipt.pk),'received_at':receipt.received_at.isoformat(),
                             'request_id':str(operation_id),'author_person_id':str(actor.person.pk)})
        event(actor,'BORRADOR_SINCRONIZADO' if action=='sync' else 'MEDICION_CREADA',ver.pk,measurement=meas,
              correlation=operation_id,detail={'before':before,'revision':ver.edit_revision,
                 'after':{'measured_at':ver.measured_at.isoformat(),'methodology':ver.methodology,'values':ver.values}})
        return response
    if action=='queue_status':
        _keys(data,['device_id','pending','conflicts'],['device_id','pending','conflicts'])
        for key in ('pending','conflicts'): require(type(data[key]) is int and 0<=data[key]<=500,'Conteo inválido.','C11',400)
        require(data['conflicts']<=data['pending'],'Conteo inconsistente.','C11',400)
        device=uuid.UUID(data['device_id'])
        row,_=m.QueueStatus.objects.update_or_create(actor=actor.person,device_id=device,
            defaults={'pending':data['pending'],'conflicts':data['conflicts'],'received_at':now})
        event(actor,'ESTADO_COLA_RECIBIDO',row.pk)
        return {'received_at':now.isoformat(),'status':'RECIBIDO'}
    raise DomainError('Operación desconocida.','OPERACION',400)


def execute(account_id,action,target,data,request_id):
    actor=actor_for(account_id)
    try:
        require(action in ACTIONS,'Operación desconocida.','OPERACION',400)
        require(isinstance(data,dict),'Objeto JSON requerido.','CAMPOS',400)
        operation_id=uuid.UUID(str(request_id))
        digest=hashlib.sha256(json.dumps({'action':'capture:'+action,'target':str(target),'data':data},
                    sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        with transaction.atomic():
            person_ids={actor.person.pk}
            if action in ('link_owner','assign_tech','assign_reviewer') and data.get('person_id'):
                person_ids.add(uuid.UUID(data['person_id']))
            list(m.Person.objects.select_for_update().filter(pk__in=person_ids).order_by('pk'))
            actor=actor_for(account_id,lock=True)
            ctx=_context(actor,action,target,data)
            prior=m.Operation.objects.filter(actor=actor.person,request_id=operation_id).first()
            if prior:
                require(prior.digest==digest,'El UUID ya fue usado con otro contenido.','IDEMPOTENCIA',409)
                return prior.response
            response=_mutate(actor,action,data,ctx,operation_id)
            m.Operation.objects.create(actor=actor.person,request_id=operation_id,action='capture:'+action,digest=digest,response=response)
            return response
    except (DomainError,IntegrityError,ObjectDoesNotExist,ValidationError,ValueError,TypeError,KeyError) as exc:
        if isinstance(exc,DomainError): error=exc
        elif isinstance(exc,IntegrityError): error=DomainError('Conflicto de registros; no se confirmó la operación.','INTEGRIDAD',409)
        elif isinstance(exc,ObjectDoesNotExist): error=DomainError('Objeto no disponible.','OBJETO',404)
        else: error=DomainError('Identificador o datos inválidos.','CAMPOS',400)
        event(actor,'CAPTURA_DENEGADA',str(target)[:64],result='DENEGADO',rule=error.rule,
              detail={'operation':str(action)[:40]})
        raise error from exc
