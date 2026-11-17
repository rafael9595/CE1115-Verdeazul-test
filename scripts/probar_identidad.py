"""Prueba HTTP repetible P1→P2→P3→P4; necesita un administrador ya configurado.

Crea identidades y datos sintéticos nuevos. Al terminar deshabilita las cuentas
creadas, conserva la evidencia y nunca modifica las credenciales del operador.
"""
import argparse
import json
import os
import re
import secrets
import uuid
from pathlib import Path
from urllib.parse import urlparse
import pyotp
from probar_integracion import Session, ROOT
from certificados import verify_certificate, fingerprint
from certificados.core import load_public_key
from certificados.demo import sample_payload


def expect(response, expected=200):
    status, body=response
    if status!=expected:
        raise RuntimeError(f'Respuesta inesperada: HTTP {status}; se esperaba {expected}. Revise la bitácora del sistema.')
    return body


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://localhost:8000')
    parser.add_argument('--admin',default='administrador')
    parser.add_argument('--out',type=Path,default=ROOT/'salida_identidad')
    args=parser.parse_args()
    if urlparse(args.url).hostname not in ('localhost','127.0.0.1'):
        parser.error('Solo se permite esta prueba en el entorno local.')
    if args.out.exists():parser.error('La carpeta de salida ya existe; use otro nombre --out.')
    cfg=json.loads((ROOT/'.local/config.json').read_text(encoding='utf-8'))
    password=os.environ.get('DEMO_PASSWORD') or cfg['DEMO_PASSWORD']
    trusted_path=os.environ.get('VERDEAZUL_TRUSTED_PUBLIC_KEYS') or cfg['VERDEAZUL_TRUSTED_PUBLIC_KEYS']
    public=Path(trusted_path.split(os.pathsep)[0]).read_bytes()
    trust=[fingerprint(load_public_key(public))]
    admin=Session(args.url);panel=admin.login(args.admin,password)
    if panel['role']!='ADMINISTRADOR':parser.error('Seleccione el rol activo Administrador antes de ejecutar la prueba.')
    marker=uuid.uuid4().hex[:10];created=[];clients={};accounts={}
    def action(session,name,target='new',data=None):
        return json.loads(expect(session.request(f'/api/identity/action/{name}/{target}/',data or {})))
    def capture(session,name,target='new',data=None,status=200):
        return json.loads(expect(session.request(f'/api/capture/action/{name}/{target}/',data or {},operation=uuid.uuid4()),status))
    try:
        print('Creando cuentas sintéticas y comprobando activación y MFA...',flush=True)
        for role in ['TECNICO','VERIFICADOR','PROPIETARIO']:
            username='p1-'+role.lower()+'-'+marker
            created_data=action(admin,'create',data={'username':username,'work_id':username.upper(),
                'primary_role':role,'additional_roles':[],'reason':'Prueba integrada P1',
                'verification_reference':'Identidad sintética de prueba '+marker})
            aid=created_data['account_id'];created.append(aid);accounts[role]=aid
            newpassword=secrets.token_urlsafe(32)
            client=Session(args.url);client.username=username;client.password=newpassword
            expect(client.request('/identity/recover/'))
            body=expect(client.request('/identity/recover/',{'token':created_data['activation_code'],
                'password':newpassword,'confirm':newpassword,'code':''},form=True)).decode()
            match=re.search(r'id="mfa-secret">([A-Z2-7]+)</code>',body)
            if not match:raise RuntimeError('La activación no llegó a la configuración MFA. Revise conectividad de la comprobación de contraseñas.')
            secret=match.group(1);otp=pyotp.TOTP(secret).now()
            expect(client.request('/api/workspace/'),401)
            body=expect(client.request('/identity/mfa/setup/',{'code':otp},form=True)).decode()
            codes=re.findall(r'class="recovery-code">([a-f0-9]{32})</code>',body)
            if len(codes)!=8:raise RuntimeError('No se entregaron los códigos de recuperación esperados.')
            client.credentials={'password':newpassword,'mfa_secret':secret,'recovery_codes':codes}
            clients[role]=client
            expect(client.request('/api/workspace/'))
            # Otra sesión no entra con contraseña solamente; tampoco reutiliza el OTP de alta.
            probe=Session(args.url);probe.username=username;probe.password=newpassword
            expect(probe.request('/login/'))
            expect(probe.request('/login/',{'username':username,'password':newpassword},form=True))
            expect(probe.request('/api/workspace/'),401)
            expect(probe.request('/identity/mfa/',{'code':otp},form=True))
            expect(probe.request('/api/workspace/'),401)
            used_code=codes.pop()
            expect(probe.request('/identity/mfa/',{'code':used_code},form=True))
            expect(probe.request('/api/workspace/'))
            expect(probe.request('/logout/',{},form=True))
            expect(probe.request('/api/workspace/'),401)
            expect(probe.request('/login/',{'username':username,'password':newpassword},form=True))
            expect(probe.request('/identity/mfa/',{'code':used_code},form=True))
            expect(probe.request('/api/workspace/'),401)
        tech,reviewer,owner=(clients[r] for r in ['TECNICO','VERIFICADOR','PROPIETARIO'])
        panels={r:json.loads(expect(c.request('/api/workspace/'))) for r,c in clients.items()}
        expect(tech.request('/api/identity/accounts/'),403)
        print('Comprobando captura, revisión y certificado firmado...',flush=True)
        oid=capture(admin,'create_owner',data={'name':'Propietario sintético P1 '+marker,'contact':'p1@example.invalid'})['owner_id']
        capture(admin,'link_owner',oid,{'person_id':panels['PROPIETARIO']['person_id'],'verification_reference':'Prueba P1'})
        farm=capture(admin,'create_farm',data={'registry_number':'P1-'+marker,'name':'Finca identidad '+marker,
            'owner_id':oid,'area_ha':'10.50','polygon':sample_payload()['farm']['polygon_wgs84']})['farm_id']
        capture(admin,'assign_tech',farm,{'person_id':panels['TECNICO']['person_id'],'reason':'Prueba P1'})
        status,result=admin.action('open_period','new',{'name':'Identidad '+marker})
        if status!=200:raise RuntimeError('No se abrió el período de prueba.')
        period=result['period_id']
        from datetime import datetime,timezone
        fields={'farm_id':farm,'period_id':period,'measured_at':datetime.now(timezone.utc).date().isoformat(),
                'methodology':'Prueba integrada de identidad','values':[{'name':'carbono_reportado','value':'145.00','unit':'tCO2e'}]}
        version=capture(tech,'create_measurement',data=fields)
        capture(admin,'assign_reviewer',version['measurement_id'],{'person_id':panels['VERIFICADOR']['person_id'],'reason':'Revisión independiente'})
        status,_=tech.action('approve',version['version_id'])
        if status!=403:raise RuntimeError('No se rechazó la aprobación por el técnico.')
        status,_=tech.action('submit',version['version_id'],{'expected_revision':version['edit_revision']})
        if status!=200:raise RuntimeError('No se envió la medición.')
        status,result=reviewer.action('approve',version['version_id'])
        if status!=200:raise RuntimeError('No se aprobó la medición.')
        cid=result['certificate_id']
        original=expect(owner.request(f'/api/certificates/{cid}/download/'))
        if not verify_certificate(original,trust).accepted:raise RuntimeError('La firma original no es válida.')
        altered=json.loads(original);altered['payload']['measurement']['values'][0]['value']='9999.00'
        altered=json.dumps(altered,ensure_ascii=False,indent=2).encode()
        if verify_certificate(altered,trust).accepted:raise RuntimeError('Se aceptó el archivo alterado.')
        sessions=json.loads(expect(tech.request('/api/identity/sessions/')))['sessions']
        current=next(s for s in sessions if s['current'])
        expect(admin.request(f'/api/identity/sessions/{current["id"]}/revoke/',{}))
        expect(tech.request('/api/workspace/'),401)
        capture(tech,'sync',data={**fields,'version_id':None,'base_revision':0,
            'captured_at':datetime.now(timezone.utc).isoformat(),'author_person_id':panels['TECNICO']['person_id']},status=401)
        result={'resultado':'OK','cuentas_y_activacion':True,'mfa_obligatorio':True,
            'codigo_totp_no_reutilizable':True,'recuperacion_un_solo_uso':True,
            'permisos_de_identidad':True,'captura_revision_y_firma':True,'alteracion_rechazada':True,
            'sesion_revocada_rechazada':True,'sincronizacion_sin_sesion_rechazada':True,
            'certificate_id':cid,'measurement_id':version['measurement_id'],'farm_id':farm}
        args.out.mkdir(parents=True)
        (args.out/'certificado_original.json').write_bytes(original)
        (args.out/'certificado_alterado.json').write_bytes(altered)
        (args.out/'clave_publica.pem').write_bytes(public)
        (args.out/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    finally:
        for aid in created:
            status,_=admin.request(f'/api/identity/action/disable/{aid}/',{'reason':'Fin de prueba sintética P1'})
            if status!=200:print(f'No se pudo deshabilitar la cuenta sintética {aid}. Revísela en Cuentas.',flush=True)


if __name__=='__main__':
    try:main()
    except (RuntimeError,AssertionError) as exc:raise SystemExit(str(exc))
