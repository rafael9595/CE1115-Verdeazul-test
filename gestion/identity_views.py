import io
import json
from datetime import datetime, timezone as dt_timezone
from functools import wraps
import pyotp
import segno
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.db import IntegrityError, transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from . import identity as i, models as m
from .policy import Actor, DomainError, actor_for, require, request_identity
from .services import event, _keys
from .views import protected, _unique


def public_errors(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        try:
            return view(request,*args,**kwargs)
        except DomainError as exc:
            if request.path.startswith('/api/'):
                return JsonResponse({'error':str(exc),'rule':exc.rule}, status=exc.status)
            return render(request,'message.html',{'error':str(exc)},status=exc.status)
    return wrapped


@public_errors
@sensitive_post_parameters()
@require_http_methods(['GET','POST'])
def login_view(request):
    error = ''
    if request.method == 'POST':
        account = i.password_check(request.POST.get('username',''),request.POST.get('password',''))
        if account:
            with i.locked_accounts(account.pk) as accounts:
                current = accounts[account.pk]
                require(current.credential_version==account.credential_version and current.is_active,rule='C1',status=401)
                i.set_pending(request,current)
                if i.mfa_required(current) or current.must_change_password:
                    return redirect('mfa_challenge' if m.MFADevice.objects.filter(account=current,confirmed=True).exists() else 'mfa_setup')
                i.start_session(request,current)
                return redirect('dashboard')
        error = 'No se pudo iniciar sesión. Tras diez fallos en quince minutos se aplica una pausa de quince minutos.'
    return render(request,'login.html',{'error':error,'local':settings.LOCAL})


@public_errors
@sensitive_post_parameters()
@require_http_methods(['GET','POST'])
def mfa_challenge(request):
    account = i.pending_account(request)
    error = ''
    if request.method == 'POST':
        with i.locked_accounts(account.pk):
            account = i.pending_account(request)
            if i.factor_check(account.pk,request.POST.get('code','')):
                i.start_session(request,account,mfa=True)
                return redirect('password_change' if account.must_change_password else 'dashboard')
            error = 'Código incorrecto, ya utilizado o acceso temporalmente pausado. Si acaba de usarlo, espere el siguiente código.'
    return render(request,'identity/challenge.html',{'error':error})


def enrollment_account(request):
    if request.user.is_authenticated:
        # El alta de un factor exige conocer la contraseña recientemente.
        require(0 <= timezone.now().timestamp()-request.session.get('reauth_at',0)<=300,
                'Inicie sesión nuevamente antes de configurar el segundo factor.', 'REAUTH',403)
        return request.user
    return i.pending_account(request)


@public_errors
@sensitive_post_parameters()
@require_http_methods(['GET','POST'])
def mfa_setup(request):
    account = enrollment_account(request)
    error = ''
    with i.locked_accounts(account.pk) as accounts:
        current = accounts[account.pk]
        require(current.is_active and current.credential_version==account.credential_version,rule='C1',status=401)
        device = m.MFADevice.objects.filter(account=current).first()
        require(device is None or not device.confirmed,'El segundo factor ya está configurado. Utilice el flujo de recuperación para reemplazarlo.','MFA',409)
        if device is None or timezone.now()-device.created_at>timezone.timedelta(minutes=10):
            secret = pyotp.random_base32()
            device,_ = m.MFADevice.objects.update_or_create(account=current, defaults={
                'encrypted_secret':i.cipher().encrypt(secret.encode()).decode(),
                'confirmed':False,'last_counter':-1,'created_at':timezone.now()})
        secret = i.decrypt(device)
        if request.method == 'POST':
            row = i.throttle(i.throttle_key(current))
            counter = int(timezone.now().timestamp())//30
            code = request.POST.get('code','').strip()
            matched = next((c for c in (counter,counter-1,counter+1)
                if pyotp.utils.strings_equal(pyotp.TOTP(secret).at(c*30),code)),None)
            if not i.blocked(row) and matched is not None:
                device.confirmed,device.last_counter = True,matched
                device.save(update_fields=['confirmed','last_counter'])
                codes = i.new_recovery_codes(current)
                i.revoke_account(current)
                # Enrolar cambia las credenciales; se crea una sesión nueva completa.
                logout(request)
                i.start_session(request,current,mfa=True)
                event(Actor(current),'MFA_ACTIVADO',current.pk)
                return render(request,'identity/codes.html',{'codes':codes,'must_change':current.must_change_password})
            if not i.blocked(row):
                i.failed(row,current)
            error = 'Código incorrecto o acceso temporalmente pausado.'
    return render(request,'identity/setup.html',{'secret':secret,'username':account.username,'error':error})


@public_errors
@require_GET
def mfa_qr(request):
    account = enrollment_account(request)
    device = m.MFADevice.objects.filter(account=account,confirmed=False).first()
    require(device is not None and timezone.now()-device.created_at<timezone.timedelta(minutes=10),rule='MFA',status=404)
    uri = pyotp.TOTP(i.decrypt(device)).provisioning_uri(name=account.username,issuer_name='Verdeazul')
    buffer = io.BytesIO()
    segno.make(uri,micro=False).save(buffer,kind='svg',scale=5)
    return HttpResponse(buffer.getvalue(),content_type='image/svg+xml')


@protected
@require_POST
def logout_view(request):
    actor = actor_for(request.user.pk)
    m.AuthSession.objects.filter(key_digest=i.digest(request.session.session_key),revoked_at__isnull=True).update(revoked_at=timezone.now())
    event(actor,'LOGOUT')
    logout(request)
    return redirect('login')


@protected
@sensitive_post_parameters()
@require_http_methods(['GET','POST'])
def reauthenticate(request):
    if not m.MFADevice.objects.filter(account=request.user,confirmed=True).exists():
        return redirect('mfa_setup')
    error = ''
    if request.method == 'POST':
        with i.locked_accounts(request.user.pk):
            actor_for(request.user.pk)
            if i.factor_check(request.user.pk,request.POST.get('code',''),request.POST.get('password','')):
                request.session['reauth_at'] = timezone.now().timestamp()
                request.session['mfa'] = True
                event(actor_for(request.user.pk),'REAUTH_OK')
                messages.success(request,'Identidad confirmada por cinco minutos.')
                return redirect('profile')
            error = 'No se pudo confirmar la identidad. Revise contraseña y código; los códigos ya usados no se aceptan.'
    return render(request,'identity/reauth.html',{'error':error},status=403 if error else 200)


@protected
@require_http_methods(['GET','POST'])
def profile(request):
    if request.method == 'POST':
        i.require_sensitive(request)
        _keys(request.POST.dict(),['email','csrfmiddlewaretoken'],['email'])
        with i.locked_accounts(request.user.pk) as accounts:
            actor_for(request.user.pk)
            i._profile_fields(accounts[request.user.pk],request.POST.dict())
            event(actor_for(request.user.pk),'CONTACTO_PROPIO_MODIFICADO',request.user.pk,rule='O1')
        messages.success(request,'Contacto actualizado.')
        return redirect('profile')
    data = i.safe_profile(request.user)
    event(actor_for(request.user.pk),'PERFIL_PROPIO_CONSULTADO',request.user.pk,rule='O1')
    return render(request,'identity/profile.html',{'profile':data,'roles':[(r,m.Role(r).label) for r in sorted(request.user.person.direct_roles)]})


@protected
@sensitive_post_parameters()
@require_http_methods(['GET','POST'])
def password_change(request):
    if request.method == 'POST':
        require(request.POST.get('password')==request.POST.get('confirm'),'Las contraseñas no coinciden.','CONTRASENA',400)
        i.require_sensitive(request)
        i.validate_new_password(request.user,request.POST.get('password',''))
        with i.locked_accounts(request.user.pk) as accounts:
            actor_for(request.user.pk)
            account = accounts[request.user.pk]
            require(not account.check_password(request.POST['password']),'Elija una contraseña distinta de la anterior.','CONTRASENA',400)
            account.set_password(request.POST['password'])
            account.must_change_password = False
            account.save(update_fields=['password','must_change_password'])
            i.revoke_account(account)
            event(Actor(account),'CONTRASENA_CAMBIADA',account.pk,rule='O1')
            logout(request)
        messages.success(request,'Contraseña actualizada. Las sesiones anteriores se revocaron. Inicie sesión nuevamente.')
        return redirect('login')
    return render(request,'identity/password.html')


@protected
@require_POST
def switch_role(request):
    i.require_sensitive(request)
    with i.locked_accounts(request.user.pk) as accounts:
        actor_for(request.user.pk)
        account = accounts[request.user.pk]
        role = request.POST.get('role','')
        require(role in account.person.direct_roles,'Rol no asignado.','ROLES',403)
        require(i.auditor_active(account.person,role),'Encargo de auditor vencido.','C6',403)
        request.session['active_role'] = role
        m.AuthSession.objects.filter(key_digest=i.digest(request.session.session_key)).update(role=role)
        event(Actor(account),'ROL_ACTIVO_CAMBIADO',account.pk,detail={'active_role':role})
    return redirect('dashboard')


@protected
@require_GET
def sessions(request):
    data = i.session_list(request)
    if request.path.startswith('/api/'):
        return JsonResponse({'sessions':data})
    return render(request,'identity/sessions.html',{'sessions':data})


@protected
@require_POST
def revoke_session(request,session_id):
    with transaction.atomic():
        actor = actor_for(request.user.pk)
        session = m.AuthSession.objects.select_for_update(of=('self',)).select_related('account__person').get(pk=session_id)
        own = session.account.person_id == actor.person.pk
        require(actor.role==m.Role.ADMIN or (own and actor.role!=m.Role.SECURITY),rule='O15',status=403)
        if not own:
            i.require_sensitive(request)
        session.revoked_at = timezone.now()
        session.save(update_fields=['revoked_at'])
        event(actor,'SESION_REVOCADA',session.pk,rule='O15')
    if i.digest(request.session.session_key)==session.key_digest:
        logout(request)
        return redirect('login')
    if request.path.startswith('/api/'):
        return JsonResponse({'status':'REVOCADA'})
    return redirect('sessions')


@protected
@require_GET
def accounts(request):
    rows = i.account_list(request.user.pk)
    versions = dict(m.Person.objects.values_list('id','auth_version'))
    for row in rows:
        import uuid
        row['version'] = versions[uuid.UUID(row['person_id'])]
    if request.path.startswith('/api/'):
        return JsonResponse({'accounts':rows})
    return render(request,'identity/accounts.html',{'accounts':rows,'role_options':m.Role.choices,'farms':m.Farm.objects.order_by('name')})


@protected
@sensitive_post_parameters()
@require_POST
def admin_action(request,action,target):
    try:
        if request.path.startswith('/api/'):
            data = json.loads(request.body,object_pairs_hook=_unique)
            require(isinstance(data,dict),rule='CAMPOS',status=400)
        else:
            data = {k:v for k,v in request.POST.items() if k!='csrfmiddlewaretoken'}
            if 'additional_roles' in data:
                data['additional_roles'] = request.POST.getlist('additional_roles')
            if action in ('create','roles'):
                data.setdefault('additional_roles',[])
            if action=='recovery':
                data['reset_mfa'] = data.get('reset_mfa')=='on'
        result = i.admin_action(request,action,None if target=='new' else int(target),data)
    except (DomainError,IntegrityError,ValueError,TypeError) as exc:
        error = exc if isinstance(exc,DomainError) else DomainError('Datos inválidos o registro duplicado.','O1',400)
        event(actor_for(request.user.pk),'IDENTIDAD_DENEGADA',str(target)[:64],result='DENEGADO',rule=error.rule,detail={'operation':action[:40]})
        raise error
    if request.path.startswith('/api/'):
        return JsonResponse(result)
    if 'activation_code' in result:
        return render(request,'identity/ticket.html',result)
    messages.success(request,'Operación de identidad confirmada.')
    return redirect('accounts')


@public_errors
@sensitive_post_parameters()
@require_http_methods(['GET','POST'])
def recover(request):
    error = ''
    if request.method=='POST':
        require(request.POST.get('password')==request.POST.get('confirm'),'Las contraseñas no coinciden.','CONTRASENA',400)
        account = i.redeem_ticket(request,request.POST.get('token',''),request.POST.get('password',''),request.POST.get('code',''))
        if account:
            return redirect('mfa_setup' if not m.MFADevice.objects.filter(account=account,confirmed=True).exists() else 'mfa_challenge')
        error = 'Segundo factor incorrecto, usado o acceso temporalmente pausado.'
    return render(request,'identity/recover.html',{'error':error})


@protected
@require_POST
def recovery_codes(request):
    i.require_sensitive(request)
    with i.locked_accounts(request.user.pk) as accounts:
        actor_for(request.user.pk)
        codes = i.new_recovery_codes(accounts[request.user.pk])
        event(actor_for(request.user.pk),'CODIGOS_RECUPERACION_RENOVADOS',request.user.pk)
    return render(request,'identity/codes.html',{'codes':codes})
