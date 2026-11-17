import json
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.middleware.csrf import get_token
from django.shortcuts import render,redirect
from django.views.decorators.http import require_GET,require_POST,require_http_methods
from . import capture,models as m
from .views import protected,_unique
from .policy import actor_for,require,DomainError
from .services import execute as business_execute

ASSETS=Path(settings.BASE_DIR)/'assets'


@protected
@require_GET
def farms(request): return render(request,'capture/farms.html',capture.catalog(request.user.pk))


@protected
@require_GET
def owner_list(request): return render(request,'capture/owners.html',capture.owners(request.user.pk))


@protected
@require_GET
def assignment_list(request): return render(request,'capture/assignments.html',capture.assignments(request.user.pk))


@protected
@require_GET
def queue_list(request): return render(request,'capture/queues.html',capture.queue_status(request.user.pk))


@protected
@require_GET
def api_catalog(request): return JsonResponse(capture.catalog(request.user.pk))


@protected
@require_GET
def api_farm(request,farm_id): return JsonResponse(capture.catalog(request.user.pk,farm_id))


@protected
@require_GET
def api_owners(request): return JsonResponse(capture.owners(request.user.pk))


@protected
@require_GET
def api_assignments(request): return JsonResponse(capture.assignments(request.user.pk))


@protected
@require_GET
def api_queues(request): return JsonResponse(capture.queue_status(request.user.pk))


@protected
@require_GET
def api_bootstrap(request):
    result=capture.bootstrap(request.user.pk); result['csrf_token']=get_token(request)
    return JsonResponse(result)


@protected
@require_POST
def api_action(request,action,target):
    try:
        data=json.loads(request.body,object_pairs_hook=_unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(data,dict): raise ValueError
    except (ValueError,UnicodeError): return JsonResponse({'error':'JSON inválido.'},status=400)
    return JsonResponse(capture.execute(request.user.pk,action,target,data,request.headers.get('Idempotency-Key','')))


@protected
@require_POST
def form_action(request,action,target):
    data={k:v for k,v in request.POST.items() if k not in ('csrfmiddlewaretoken','request_id')}
    result=capture.execute(request.user.pk,action,target,data,request.POST.get('request_id'))
    messages.success(request,'Operación confirmada.')
    return redirect('owners' if 'owner' in action else 'assignments' if action.startswith(('assign_','revoke_')) else 'farms')


@protected
@require_http_methods(['GET','POST'])
def farm_form(request,farm_id=None):
    actor=actor_for(request.user.pk); require(actor.role==m.Role.ADMIN,rule='O2')
    farm=m.Farm.objects.get(pk=farm_id) if farm_id else None
    error=''; status=200
    data={k:request.POST.get(k,'') for k in ('name','registry_number','owner_id','area_ha','coordinates','reason','expected_revision')}
    if request.method=='POST':
        try:
            polygon=[]
            for line in data['coordinates'].strip().splitlines():
                pair=[x.strip() for x in line.split(',')]
                require(len(pair)==2,'Use longitud,latitud en cada línea.','CAMPOS',400); polygon.append(pair)
            payload={k:data[k] for k in ('name','registry_number','owner_id','area_ha')}; payload['polygon']=polygon
            if farm: payload.update({'reason':data['reason'],'expected_revision':data['expected_revision']})
            capture.execute(request.user.pk,'edit_farm' if farm else 'create_farm',farm_id or 'new',payload,request.POST.get('request_id'))
            messages.success(request,'Finca guardada.'); return redirect('farms')
        except DomainError as exc: error=str(exc); status=exc.status
    elif farm:
        data={'name':farm.name,'registry_number':farm.registry_number,'owner_id':str(farm.owner_id),
              'area_ha':str(farm.area_ha),'coordinates':'\n'.join(','.join(p) for p in farm.polygon),
              'expected_revision':farm.revision}
    # O9: solamente el administrador puede obtener esta lista.
    return render(request,'capture/farm_form.html',{'data':data,'farm':farm,'owners':capture.owners(request.user.pk)['owners'],
               'error':error},status=status)


@protected
@require_http_methods(['GET','POST'])
def measurement_form(request,version_id=None):
    actor=actor_for(request.user.pk); require(actor.role==m.Role.TECH,rule='C2')
    prepared=capture.bootstrap(request.user.pk)
    initial=next((v for v in prepared['versions'] if v['id']==str(version_id)),None) if version_id else None
    if version_id: require(initial is not None,'Borrador no disponible para edición.','C2',403)
    data={}; values=[{'name':'carbono_reportado','value':'','unit':'tCO2e'}]; error=''; status=200
    if initial:
        data={**initial,'farm_id':initial['measurement']['farm_id'],'period_id':initial['measurement']['period_id'],
              'expected_revision':initial['edit_revision']}; values=initial['values']
    if request.method=='POST':
        data={k:request.POST.get(k,'') for k in ('farm_id','period_id','measured_at','methodology','expected_revision')}
        columns=[request.POST.getlist(k) for k in ('value_name','value_number','value_unit')]
        try:
            require(len({len(c) for c in columns})==1,'Filas de valores incompletas.','CAMPOS',400)
            values=[{'name':n,'value':v,'unit':u} for n,v,u in zip(*columns)]
            payload={'measured_at':data['measured_at'],'methodology':data['methodology'],'values':values}
            if initial:
                payload['expected_revision']=data['expected_revision']
                business_execute(request.user.pk,'edit',version_id,payload,request.POST.get('request_id'))
            else:
                payload.update({'farm_id':data['farm_id'],'period_id':data['period_id']})
                capture.execute(request.user.pk,'create_measurement','new',payload,request.POST.get('request_id'))
            messages.success(request,'Borrador guardado. Puede enviarlo a revisión desde el panel.'); return redirect('dashboard')
        except DomainError as exc: error=str(exc); status=exc.status
    return render(request,'capture/measurement_form.html',{'prepared':prepared,'data':data,'values':values,
                  'editing':bool(initial),'error':error},status=status)


@protected
@require_GET
def measurement_download(request,measurement_id):
    from .queries import report
    actor=actor_for(request.user.pk); require(actor.role==m.Role.OWNER,rule='O5-D')
    result=report(request.user.pk,measurement_id,download=True)
    response=JsonResponse({'measurement':result['measurement'],'versions':result['versions']},
                          json_dumps_params={'ensure_ascii':False,'indent':2})
    response['Content-Disposition']=f'attachment; filename="medicion_{measurement_id}.json"'
    return response


@require_GET
def field_shell(request):
    # No datos de usuario, tokens ni cabeceras de sesión en el recurso público cacheable.
    return HttpResponse((ASSETS/'campo.html').read_bytes(),content_type='text/html; charset=utf-8')


@require_GET
def asset(request,name):
    types={'campo.js':'text/javascript','vault.js':'text/javascript','campo.css':'text/css',
           'forms.js':'text/javascript','offline_tests.js':'text/javascript','offline_tests.html':'text/html'}
    if name not in types: raise Http404
    return HttpResponse((ASSETS/name).read_bytes(),content_type=types[name]+'; charset=utf-8')


@require_GET
def service_worker(request):
    return HttpResponse((ASSETS/'sw.js').read_bytes(),content_type='text/javascript; charset=utf-8')
