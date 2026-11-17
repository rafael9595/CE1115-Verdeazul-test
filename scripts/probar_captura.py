"""Prueba repetible de personas 2/3/4 sobre registros sintéticos nuevos."""
import argparse,json,os,sys,uuid
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
from probar_integracion import Session,ROOT
from certificados import verify_certificate,fingerprint
from certificados.core import load_public_key
from certificados.demo import sample_payload


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',default='http://localhost:8000')
    parser.add_argument('--out',type=Path,default=ROOT/'salida_captura');args=parser.parse_args()
    if urlparse(args.url).hostname not in ('localhost','127.0.0.1'):parser.error('Solo entorno local.')
    if args.out.exists():parser.error('La carpeta de salida ya existe. Use otro nombre --out para una nueva prueba.')
    cfg=json.loads((ROOT/'.local/config.json').read_text()) if (ROOT/'.local/config.json').exists() else {}
    password=os.environ.get('DEMO_PASSWORD') or cfg.get('DEMO_PASSWORD');keyfile=os.environ.get('VERDEAZUL_TRUSTED_PUBLIC_KEYS') or cfg.get('VERDEAZUL_TRUSTED_PUBLIC_KEYS')
    if not password or not keyfile:parser.error('Primero configure el entorno local.')
    sessions={};panels={}
    for name in ['administrador','supervisor','tecnico','verificador','propietario','auditor']:
        sessions[name]=Session(args.url);panels[name]=sessions[name].login(name,password)
    def cap(user,action,target='new',data=None,op=None,expected=200):
        status,body=sessions[user].request(f'/api/capture/action/{action}/{target}/',data or {},operation=op or uuid.uuid4())
        result=json.loads(body);assert status==expected,(action,status,result);return result
    marker=uuid.uuid4().hex[:10]
    owner=cap('administrador','create_owner',data={'name':'Propietario sintético '+marker,'contact':'captura-demo@example.invalid'})['owner_id']
    cap('administrador','link_owner',owner,{'person_id':panels['propietario']['person_id'],'verification_reference':'Documento sintético de prueba '+marker})
    farm=cap('administrador','create_farm',data={'registry_number':'CAPTURA-'+marker,'name':'Finca captura '+marker,'owner_id':owner,'area_ha':'10.50',
            'polygon':sample_payload()['farm']['polygon_wgs84']})['farm_id']
    cap('supervisor','assign_tech',farm,{'person_id':panels['tecnico']['person_id'],'reason':'Prueba de captura'})
    status,result=sessions['administrador'].action('open_period','new',{'name':'Captura '+marker});assert status==200,result
    period=result['period_id']
    fields={'farm_id':farm,'period_id':period,'measured_at':datetime.now(timezone.utc).date().isoformat(),
            'methodology':'Captura sintética integrada','values':[{'name':'carbono_reportado','value':'125.50','unit':'tCO2e'}]}
    cap('verificador','create_measurement',data=fields,expected=403)
    initial=cap('tecnico','create_measurement',data=fields)
    data={**fields,'version_id':initial['version_id'],'base_revision':1,'author_person_id':panels['tecnico']['person_id'],
          'captured_at':datetime.now(timezone.utc).isoformat(),'values':[{'name':'carbono_reportado','value':'130.00','unit':'tCO2e'}]}
    op=uuid.uuid4();received=cap('tecnico','sync',data=data,op=op)
    assert cap('tecnico','sync',data=data,op=op)==received,'El reintento cambió la constancia.'
    cap('tecnico','sync',data={**data,'methodology':'Intento obsoleto'},expected=409)
    cap('supervisor','assign_reviewer',initial['measurement_id'],{'person_id':panels['verificador']['person_id'],'reason':'Revisión independiente'})
    status,body=sessions['tecnico'].action('submit',initial['version_id'],{'expected_revision':received['edit_revision']});assert status==200,body
    status,body=sessions['verificador'].action('approve',initial['version_id']);assert status==200,body
    cert=body['certificate_id'];status,raw=sessions['propietario'].request(f'/api/certificates/{cert}/download/');assert status==200
    public=Path(keyfile.split(os.pathsep)[0]).read_bytes();assert verify_certificate(raw,[fingerprint(load_public_key(public))]).accepted
    report_status,body=sessions['propietario'].request(f'/api/reports/{initial["measurement_id"]}/');assert report_status==200
    assert json.loads(body)['owner']['name'].endswith(marker)
    # El auditor no obtiene acceso a una finca nueva sin un encargo vigente.
    status,_=sessions['auditor'].request(f'/api/reports/{initial["measurement_id"]}/');assert status==403
    cap('tecnico','queue_status',data={'device_id':str(uuid.uuid4()),'pending':0,'conflicts':0})
    status,bootstrap=sessions['tecnico'].request('/api/capture/bootstrap/');assert status==200
    assert 'captura-demo@example.invalid' not in bootstrap.decode()
    for path in ('/campo/','/campo/sw.js','/assets/vault.js','/assets/campo.js','/assets/offline_tests.html'):
        assert sessions['tecnico'].request(path)[0]==200,path
    result={'resultado':'OK','farm_id':farm,'measurement_id':initial['measurement_id'],'certificate_id':cert,
      'propietario_y_finca_creados':True,'asignaciones_aplicadas':True,'captura_solo_tecnico':True,'sincronizacion_confirmada':True,
      'reintento_sin_duplicar':True,'conflicto_sin_sobrescritura':True,'revision_y_firma_integradas':True,
      'propietario_descarga_su_certificado':True,'auditor_sin_encargo_rechazado':True,
      'scope':'Prueba HTTP de personas 2/3/4. El recorrido sin red en un navegador requiere la guía de captura.'}
    args.out.mkdir(parents=True)
    (args.out/'certificado_captura.json').write_bytes(raw);(args.out/'clave_publica.pem').write_bytes(public)
    (args.out/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
