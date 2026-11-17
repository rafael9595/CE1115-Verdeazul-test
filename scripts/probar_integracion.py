"""Prueba real por HTTP del backend y del módulo original de certificados.

Utiliza las fincas A y B de una carga de demostración nueva. No borra ni reinicia datos.
"""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler
import uuid
import getpass
import time
import pyotp

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from certificados import verify_certificate, fingerprint
from certificados.core import load_public_key


class Session:
    def __init__(self,base):
        self.base=base.rstrip('/')
        self.jar=http.cookiejar.CookieJar()
        self.client=build_opener(ProxyHandler({}),HTTPCookieProcessor(self.jar))
        self.username = None
        self.credentials = None
        self.last_url = ''

    def factor_code(self):
        if self.credentials:
            codes=self.credentials.get('recovery_codes',[])
            if codes:
                code=codes.pop(0)
                if os.environ.get('VERDEAZUL_TEST_CREDENTIALS_FILE'):
                    path=Path(os.environ['VERDEAZUL_TEST_CREDENTIALS_FILE'])
                    current=json.loads(path.read_text(encoding='utf-8'))
                    current[self.username]=self.credentials
                    path.write_text(json.dumps(current),encoding='utf-8')
                return code
            secret=self.credentials.get('mfa_secret')
            if secret:
                # Solo fixture de prueba local: evitar reutilizar el código del mismo intervalo.
                now=int(time.time())//30
                while now <= self.credentials.get('last_counter',-1):
                    time.sleep(1);now=int(time.time())//30
                self.credentials['last_counter']=now
                return pyotp.TOTP(secret).at(now*30)
        if not sys.stdin.isatty():
            raise RuntimeError('La prueba necesita el segundo factor en una terminal interactiva.')
        return getpass.getpass(f'Código del autenticador o de recuperación para {self.username}: ')

    def request(self,path,data=None,form=False,operation=None):
        if path=='/reauth/' and data is not None and 'code' not in data:
            data={**data,'password':self.password,'code':self.factor_code()}
        headers={}
        raw=None
        if data is not None:
            token=next((c.value for c in self.jar if c.name=='csrftoken'),'')
            headers={'X-CSRFToken':token,'Referer':self.base+path}
            if form:
                raw=urlencode(data).encode(); headers['Content-Type']='application/x-www-form-urlencoded'
            else:
                raw=json.dumps(data).encode(); headers['Content-Type']='application/json'
        if operation: headers['Idempotency-Key']=str(operation)
        try:
            with self.client.open(Request(self.base+path,data=raw,headers=headers),timeout=30) as response:
                self.last_url=response.url
                if os.environ.get('VERDEAZUL_HTTP_TRACE')=='1':
                    print(('POST' if raw is not None else 'GET'),path,response.status,'->',urlparse(response.url).path,file=sys.stderr)
                return response.status,response.read()
        except HTTPError as exc:
            if os.environ.get('VERDEAZUL_HTTP_TRACE')=='1':
                print(('POST' if raw is not None else 'GET'),path,exc.code,file=sys.stderr)
            return exc.code,exc.read()

    def login(self,username,password):
        self.username=username
        fixture_path=os.environ.get('VERDEAZUL_TEST_CREDENTIALS_FILE')
        if fixture_path:
            self.credentials=json.loads(Path(fixture_path).read_text(encoding='utf-8')).get(username)
            if self.credentials:password=self.credentials['password']
        self.password=password
        status,_=self.request('/login/')
        assert status==200,'No se pudo abrir el inicio de sesión.'
        status,_=self.request('/login/',{'username':username,'password':password},form=True)
        if self.last_url.endswith('/login/') and sys.stdin.isatty():
            self.password=getpass.getpass(f'Contraseña actual de {username}: ')
            status,_=self.request('/login/',{'username':username,'password':self.password},form=True)
        if self.last_url.endswith('/identity/mfa/'):
            status,_=self.request('/identity/mfa/',{'code':self.factor_code()},form=True)
        if self.last_url.endswith(('/identity/mfa/setup/','/identity/password/')):
            raise RuntimeError(f'Complete primero el acceso de {username} en el navegador: segundo factor y contraseña individual.')
        status,body=self.request('/api/workspace/')
        assert status==200,'Inicio de sesión fallido.'
        return json.loads(body)

    def action(self,action,target,data=None,operation=None):
        status,body=self.request(f'/api/action/{action}/{target}/',data or {},operation=operation or uuid.uuid4())
        return status,json.loads(body)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://localhost:8000')
    parser.add_argument('--out',type=Path,default=ROOT/'salida_prueba')
    args=parser.parse_args()
    if urlparse(args.url).hostname not in ('localhost','127.0.0.1'):
        parser.error('Esta prueba solo utiliza el entorno local.')
    config={}
    if (ROOT/'.local/config.json').exists(): config=json.loads((ROOT/'.local/config.json').read_text())
    password=os.environ.get('DEMO_PASSWORD') or config.get('DEMO_PASSWORD')
    keyfile=os.environ.get('VERDEAZUL_TRUSTED_PUBLIC_KEYS') or config.get('VERDEAZUL_TRUSTED_PUBLIC_KEYS')
    if not password or not keyfile: parser.error('Primero ejecute scripts/setup_local.py.')
    if args.out.exists(): parser.error('La carpeta de salida ya existe; utilice --out con un nombre nuevo.')
    public=Path(keyfile.split(os.pathsep)[0]).read_bytes()
    trusted=[fingerprint(load_public_key(public))]
    reviewer=Session(args.url); panel=reviewer.login('verificador',password)
    candidates=[v for v in panel['versions'] if v['measurement']['farm'].startswith('A ·') and v['status']=='ENVIADA']
    returned=[v for v in panel['versions'] if v['measurement']['farm'].startswith('B ·') and v['status']=='ENVIADA']
    if len(candidates)!=1:
        parser.error('La finca A ya fue procesada. No se altera el historial: use la guía manual o una base de prueba nueva.')
    if len(returned)!=1:
        parser.error('La finca B ya fue procesada. Use la guía manual o una base de prueba nueva.')
    version=candidates[0]['id']
    technician=Session(args.url); technician.login('tecnico',password)
    status,_=technician.action('approve',version)
    assert status==403,'El técnico pudo aprobar o la respuesta fue inesperada.'
    operation=uuid.uuid4()
    status,result=reviewer.action('approve',version,operation=operation)
    assert status==200,result
    cert_id=result['certificate_id']
    status,repeated=reviewer.action('approve',version,operation=operation)
    assert status==200 and repeated==result,'El reintento duplicó o cambió la respuesta.'
    status,original=reviewer.request(f'/api/certificates/{cert_id}/download/')
    assert status==200,'No se pudo descargar el certificado.'
    original_result=verify_certificate(original,trusted)
    assert original_result.accepted,'El documento emitido no verifica con la clave de confianza.'
    tampered=json.loads(original)
    tampered['payload']['measurement']['values'][0]['value']='9999.00'
    altered=json.dumps(tampered,ensure_ascii=False,indent=2).encode()
    altered_result=verify_certificate(altered,trusted)
    assert not altered_result.accepted,'La modificación no fue detectada.'
    admin=Session(args.url); admin.login('administrador',password)
    status,body=admin.request('/api/audit/')
    assert status==200 and any(e['action']=='CERTIFICADO_EMITIDO' and e['object_id']==cert_id
                              for e in json.loads(body)['events']),'No se encontró el evento de emisión.'
    # Mismos manejadores POST utilizados por los formularios de la interfaz.
    def form(session,action,target,data=None):
        data={**(data or {}),'request_id':str(uuid.uuid4())}
        if action in ('edit','submit'):
            _,body=session.request('/api/workspace/')
            data['expected_revision']=next(v['edit_revision'] for v in json.loads(body)['versions'] if v['id']==target)
        status,_=session.request(f'/action/{action}/{target}/',data,form=True)
        assert status==200,f'Formulario {action}: HTTP {status}'
    source=returned[0]
    form(reviewer,'return',source['id'],{'reason':'Corregir medición sintética'})
    form(technician,'correct',source['id'],{'amendment_id':''})
    status,body=technician.request('/api/workspace/')
    correction=next(v for v in json.loads(body)['versions'] if v['source_id']==source['id'])
    form(technician,'edit',correction['id'],{'measured_at':correction['measured_at'],
         'methodology':'Corrección comprobada mediante formularios HTTP',
         'values':json.dumps([{'name':'carbono_reportado','value':'120.00','unit':'tCO2e'}])})
    form(technician,'submit',correction['id'])
    form(reviewer,'approve',correction['id'])
    status,body=reviewer.request('/api/workspace/')
    versions={v['id']:v['status'] for v in json.loads(body)['versions']}
    assert versions[source['id']]=='DEVUELTA' and versions[correction['id']]=='APROBADA'
    summary={'resultado':'OK','version_id':version,'certificate_id':cert_id,
        'tecnico_sin_permiso':True,'aprobacion_persistida':True,'reintento_mismo_certificado':True,
        'firma_original_confiable':original_result.accepted,'alteracion_rechazada':not altered_result.accepted,
        'evento_emision_presente':True,'formularios_devolucion_correccion_aprobacion':True,
        'scope':'Prueba HTTP local con datos sintéticos; no acredita despliegue en nube ni prueba visual en navegador.'}
    args.out.mkdir(parents=True)
    for name,data in [('certificado_original.json',original),('certificado_alterado.json',altered),('clave_publica.pem',public)]:
        (args.out/name).write_bytes(data)
    (args.out/'resultado.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('Evidencia guardada en:',args.out)


if __name__=='__main__': main()
