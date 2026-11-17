import json
import uuid
from datetime import datetime, timezone as dt_timezone
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from certificados import verify_certificate, fingerprint
from certificados.core import load_public_key, read_limited
from pathlib import Path
from . import services, queries, models as m
from .policy import DomainError, actor_for


def protected(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_authenticated:
            if request.path.startswith('/api/'): return JsonResponse({'error':'Inicie sesión.'},status=401)
            return redirect('login')
        try: return view(request,*args,**kwargs)
        except DomainError as exc:
            # Mutaciones ya registran la denegación al salir de su transacción.
            if request.method=='GET':
                services.event(actor_for(request.user.pk),'ACCESO_DENEGADO',result='DENEGADO',rule=exc.rule)
            if request.path.startswith('/api/'): return JsonResponse({'error':str(exc),'rule':exc.rule},status=exc.status)
            return render(request,'message.html',{'error':str(exc)},status=exc.status)
        except (ObjectDoesNotExist,ValidationError):
            return JsonResponse({'error':'Objeto no disponible.'},status=404)
    return wrapped


@protected
@require_GET
def dashboard(request):
    return render(request,'dashboard.html',{**queries.workspace(request.user.pk),'local':settings.LOCAL})


def _auth_time(request):
    value=request.session.get('reauth_at')
    return datetime.fromtimestamp(value,tz=dt_timezone.utc) if value else None


def _unique(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise ValueError('duplicado')
        out[k]=v
    return out


@protected
@require_POST
def api_action(request,action,target):
    try:
        data=json.loads(request.body,object_pairs_hook=_unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(data,dict): raise ValueError
        req_id=request.headers.get('Idempotency-Key','')
    except (ValueError,UnicodeError): return JsonResponse({'error':'JSON inválido.'},status=400)
    result=services.execute(request.user.pk,action,target,data,req_id,_auth_time(request))
    return JsonResponse(result)


@protected
@require_POST
def form_action(request,action,target):
    data={k:v for k,v in request.POST.items() if k not in ('csrfmiddlewaretoken','request_id')}
    if action=='edit':
        try: data['values']=json.loads(data['values'])
        except (ValueError,KeyError): raise DomainError('Mediciones JSON inválidas.')
    if action=='correct' and not data.get('amendment_id'): data={}
    result=services.execute(request.user.pk,action,target,data,request.POST.get('request_id'),_auth_time(request))
    messages.success(request,'Operación confirmada: '+json.dumps(result,ensure_ascii=False))
    return redirect('dashboard')


@protected
@require_GET
def api_workspace(request): return JsonResponse(queries.workspace(request.user.pk))


@protected
@require_GET
def report_view(request,measurement_id):
    download=request.GET.get('download')=='1'
    result=queries.report(request.user.pk,measurement_id,download)
    response=JsonResponse(result,json_dumps_params={'ensure_ascii':False,'indent':2})
    if download: response['Content-Disposition']=f'attachment; filename="reporte_{measurement_id}.json"'
    return response


@protected
@require_GET
def certificate_download(request,certificate_id):
    response=HttpResponse(queries.download_certificate(request.user.pk,certificate_id),content_type='application/json')
    response['Content-Disposition']=f'attachment; filename="certificado_{certificate_id}.json"'
    return response


@protected
@require_GET
def price_view(request,certificate_id): return JsonResponse(queries.read_price(request.user.pk,certificate_id))


@protected
@require_GET
def audit_view(request):
    rows=queries.audit(request.user.pk,request.GET.get('download')=='1')
    return JsonResponse({'events':rows},json_dumps_params={'ensure_ascii':False,'indent':2})


@require_http_methods(['GET','POST'])
def verify_view(request):
    result=None
    if request.method=='POST':
        uploaded=request.FILES.get('certificate')
        if uploaded is None or uploaded.size>1024*1024:
            return render(request,'verify.html',{'error':'Adjunte un JSON de hasta 1 MiB.'},status=400)
        trusted=[]
        try:
            trusted=[fingerprint(load_public_key(read_limited(Path(p),16384))) for p in settings.TRUSTED_PUBLIC_KEY_FILES]
        except (ValueError,OSError):
            return render(request,'verify.html',{'error':'No se pudo cargar la lista de confianza configurada.'},status=503)
        result=verify_certificate(uploaded.read(1024*1024+1),trusted)
        # No se guarda el archivo ni se consulta la BD: el usuario ya posee el documento.
    return render(request,'verify.html',{'result':result})


@require_GET
def health(request): return JsonResponse({'status':'ok','module':'revision-certificacion'})
