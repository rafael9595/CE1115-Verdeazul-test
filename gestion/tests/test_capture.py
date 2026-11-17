from .identity_helpers import session_for
import copy
import json
import os
import secrets
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.test import TestCase,TransactionTestCase,Client
from django.db import transaction,DatabaseError,close_old_connections
from django.utils import timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from gestion import models as m,capture as c,services as s,queries as q
from gestion.policy import DomainError
from .test_integration import fixture


class CaptureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users,cls.password,cls.farm,cls.period,cls.measurement,cls.version=fixture()

    def setUp(self):
        key=Ed25519PrivateKey.generate()
        pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
        env=patch.dict(os.environ,{'VERDEAZUL_SIGNING_PRIVATE_KEY_PEM':pem,'VERDEAZUL_SIGNING_PRIVATE_KEY_FILE':''})
        env.start();self.addCleanup(env.stop)

    def call(self,role,action,target='new',data=None,op=None):
        return c.execute(self.users[role].pk,action,str(target),data or {},op or uuid.uuid4())

    def business(self,role,action,target,data=None):
        data=data or {}
        if action in ('edit','submit') and 'expected_revision' not in data:
            data={**data,'expected_revision':m.Version.objects.get(pk=target).edit_revision}
        return s.execute(self.users[role].pk,action,str(target),data,uuid.uuid4(),timezone.now())

    def values(self):
        return {'measured_at':timezone.localdate().isoformat(),'methodology':'Metodología sintética',
                'values':[{'name':'carbono_reportado','value':'125.50','unit':'tCO2e'}]}

    def create_data(self): return {**self.values(),'farm_id':str(self.farm.pk),'period_id':str(self.period.pk)}
    def sync_data(self): return {**self.create_data(),'author_person_id':str(self.users[m.Role.TECH].person_id),
            'version_id':None,'base_revision':0,'captured_at':'2026-11-10T12:00:00-06:00'}
    def new_draft(self): return m.Version.objects.get(pk=self.call(m.Role.TECH,'create_measurement',data=self.create_data())['version_id'])
    def farm_data(self): return {'registry_number':'NEW-001','name':'Finca nueva','owner_id':str(self.farm.owner_id),
                                'area_ha':'10.5','polygon':self.farm.polygon}
    def login_client(self,role,csrf=False):
        return session_for(self.users[role],csrf=csrf)

    def test_admin_creates_owner_and_retry_does_not_duplicate(self):
        op=uuid.uuid4();data={'name':'Nombre legal','contact':'contacto@example.invalid'}
        a=self.call(m.Role.ADMIN,'create_owner',data=data,op=op);b=self.call(m.Role.ADMIN,'create_owner',data=data,op=op)
        self.assertEqual(a,b);self.assertEqual(m.Owner.objects.filter(name='Nombre legal').count(),1)

    def test_other_roles_cannot_create_owner_or_farm(self):
        for role in m.Role.values:
            if role==m.Role.ADMIN:continue
            for action,data in [('create_owner',{'name':'Persona','contact':'contacto'}),('create_farm',self.farm_data())]:
                with self.subTest(role=role,action=action),self.assertRaises(DomainError):self.call(role,action,data=data)

    def test_owner_can_update_own_contact_but_not_legal_name(self):
        self.call(m.Role.OWNER,'edit_owner',self.farm.owner_id,{'contact':'nuevo','expected_revision':1})
        self.assertEqual(m.Owner.objects.get(pk=self.farm.owner_id).contact,'nuevo')
        with self.assertRaises(DomainError):self.call(m.Role.OWNER,'edit_owner',self.farm.owner_id,{'contact':'otro','name':'Suplantado','expected_revision':2})

    def test_owner_cannot_update_foreign_owner(self):
        foreign=m.Owner.objects.create(name='Ajeno',contact='PRIVADO')
        with self.assertRaises(DomainError):self.call(m.Role.OWNER,'edit_owner',foreign.pk,{'contact':'otro','expected_revision':1})
        self.assertNotIn('PRIVADO',json.dumps(c.owners(self.users[m.Role.OWNER].pk)))

    def test_stale_owner_edit_does_not_overwrite(self):
        self.call(m.Role.ADMIN,'edit_owner',self.farm.owner_id,{'contact':'primero','expected_revision':1})
        with self.assertRaises(DomainError) as ctx:self.call(m.Role.ADMIN,'edit_owner',self.farm.owner_id,{'contact':'segundo','expected_revision':1})
        self.assertEqual(ctx.exception.status,409);self.assertEqual(m.Owner.objects.get(pk=self.farm.owner_id).contact,'primero')

    def test_owner_link_requires_verification_and_correct_role(self):
        owner=m.Owner.objects.create(name='Nuevo',contact='contacto')
        with self.assertRaises(DomainError):self.call(m.Role.ADMIN,'link_owner',owner.pk,{'person_id':str(self.users[m.Role.OWNER].person_id),'verification_reference':''})
        with self.assertRaises(DomainError):self.call(m.Role.ADMIN,'link_owner',owner.pk,{'person_id':str(self.users[m.Role.TECH].person_id),'verification_reference':'DOC-1'})
        result=self.call(m.Role.ADMIN,'link_owner',owner.pk,{'person_id':str(self.users[m.Role.OWNER].person_id),'verification_reference':'Documento de prueba verificado'})
        self.assertEqual(m.OwnerLink.objects.get(pk=result['link_id']).created_by_id,self.users[m.Role.ADMIN].person_id)
        self.assertIn(str(owner.pk),json.dumps(c.owners(self.users[m.Role.OWNER].pk)))

    def test_revoked_owner_link_removes_current_scope(self):
        link=m.OwnerLink.objects.get(owner=self.farm.owner)
        self.call(m.Role.ADMIN,'revoke_owner_link',link.pk,{'reason':'Terminó representación'})
        self.assertEqual(c.owners(self.users[m.Role.OWNER].pk)['owners'],[])
        self.assertEqual(c.catalog(self.users[m.Role.OWNER].pk)['farms'],[])

    def test_farm_creation_requires_unique_registry_and_valid_geography(self):
        result=self.call(m.Role.ADMIN,'create_farm',data=self.farm_data());self.assertTrue(m.Farm.objects.filter(pk=result['farm_id']).exists())
        with self.assertRaises(DomainError):self.call(m.Role.ADMIN,'create_farm',data=self.farm_data())
        data={**self.farm_data(),'registry_number':'INVALID','polygon':[['0','0'],['1','0'],['1','1'],['0','0']]}
        with self.assertRaises(DomainError):self.call(m.Role.ADMIN,'create_farm',data=data)
        self.assertFalse(m.Farm.objects.filter(registry_number='INVALID').exists())

    def test_stale_catalog_edit_and_signature_snapshot(self):
        cert_id=self.business(m.Role.REVIEWER,'approve',self.version.pk)['certificate_id']
        original=bytes(m.Certificate.objects.get(pk=cert_id).signed_bytes)
        data={**self.farm_data(),'registry_number':self.farm.registry_number,'name':'Nombre actualizado','expected_revision':1,'reason':'Cambio de catálogo'}
        self.call(m.Role.ADMIN,'edit_farm',self.farm.pk,data)
        with self.assertRaises(DomainError):self.call(m.Role.ADMIN,'edit_farm',self.farm.pk,data)
        self.assertEqual(bytes(m.Certificate.objects.get(pk=cert_id).signed_bytes),original)

    def test_farm_catalog_role_matrix_and_no_personal_leak(self):
        for role in m.Role.values:
            if role in (m.Role.AUDITOR,m.Role.SECURITY):
                with self.assertRaises(DomainError):c.catalog(self.users[role].pk)
            else:
                raw=json.dumps(c.catalog(self.users[role].pk));self.assertIn(str(self.farm.pk),raw)
                if role not in (m.Role.ADMIN,m.Role.OWNER):self.assertNotIn('PERSONAL_OWNER_TEST',raw)
                self.assertNotIn('PRIVATE_CONTACT_TEST',raw)

    def test_expired_assignment_without_history_removes_farm_read(self):
        f=m.Farm.objects.create(**{**self.farm_data(),'owner':self.farm.owner,'registry_number':'NO-HISTORY','polygon':self.farm.polygon,'area_ha':'1'})
        a=m.FarmAssignment.objects.create(farm=f,technician=self.users[m.Role.TECH].person)
        self.call(m.Role.SUPERVISOR,'revoke_tech',a.pk,{'reason':'Reasignación'})
        with self.assertRaises(DomainError):c.catalog(self.users[m.Role.TECH].pk,f.pk)

    def test_supervisor_assigns_and_manager_cannot(self):
        other=m.Person.objects.create(work_id='TECH-2',role=m.Role.TECH);m.Account.objects.create_user(username='t2',person=other,password=secrets.token_urlsafe(20))
        data={'person_id':str(other.pk),'reason':'Apoyo de campo'}
        with self.assertRaises(DomainError):self.call(m.Role.MANAGER,'assign_tech',self.farm.pk,data)
        result=self.call(m.Role.SUPERVISOR,'assign_tech',self.farm.pk,data)
        self.assertEqual(m.FarmAssignment.objects.get(pk=result['assignment_id']).technician,other)
        with self.assertRaises(DomainError):self.call(m.Role.SUPERVISOR,'assign_tech',self.farm.pk,data)

    def test_wrong_role_and_historical_author_cannot_be_assigned_reviewer(self):
        with self.assertRaises(DomainError):self.call(m.Role.SUPERVISOR,'assign_reviewer',self.measurement.pk,{'person_id':str(self.users[m.Role.TECH].person_id),'reason':'Revisar'})
        person=self.users[m.Role.TECH].person;m.Person.objects.filter(pk=person.pk).update(role=m.Role.REVIEWER)
        with self.assertRaises(DomainError) as ctx:self.call(m.Role.ADMIN,'assign_reviewer',self.measurement.pk,{'person_id':str(person.pk),'reason':'Revisar'})
        self.assertEqual(ctx.exception.rule,'C3')

    def test_assignment_finalization_preserves_original_technician(self):
        assignment=m.FarmAssignment.objects.get(farm=self.farm)
        self.call(m.Role.SUPERVISOR,'revoke_tech',assignment.pk,{'reason':'Cambio de equipo'})
        self.measurement.refresh_from_db();self.assertEqual(self.measurement.technician_id,self.users[m.Role.TECH].person_id)
        self.assertTrue(m.FarmAssignment.objects.filter(pk=assignment.pk).exists())
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'create_measurement',data=self.create_data())

    def test_assignment_rows_cannot_be_rewritten_or_deleted(self):
        assignment=m.FarmAssignment.objects.get(farm=self.farm)
        with self.assertRaises(DatabaseError),transaction.atomic():m.FarmAssignment.objects.filter(pk=assignment.pk).update(technician=self.users[m.Role.REVIEWER].person)
        with self.assertRaises(DatabaseError),transaction.atomic():m.FarmAssignment.objects.filter(pk=assignment.pk).delete()

    def test_assignment_views_respect_scope_and_security_projection(self):
        raw=c.assignments(self.users[m.Role.TECH].pk)
        self.assertTrue(all(x['person_id']==str(self.users[m.Role.TECH].person_id) for x in raw['assignments']))
        security=json.dumps(c.assignments(self.users[m.Role.SECURITY].pk))
        for secret in ('PRIVATE_CONTACT_TEST','PERSONAL_OWNER_TEST','125.50','polygon'):self.assertNotIn(secret,security)
        for role in (m.Role.OWNER,m.Role.AUDITOR):
            with self.assertRaises(DomainError):c.assignments(self.users[role].pk)

    def test_only_assigned_technician_can_create_measurement(self):
        for role in m.Role.values:
            if role!=m.Role.TECH:
                with self.assertRaises(DomainError):self.call(role,'create_measurement',data=self.create_data())
        v=self.new_draft();self.assertEqual(v.author_id,self.users[m.Role.TECH].person_id);self.assertEqual(v.status,'BORRADOR')

    def test_creation_rejects_author_spoof_and_incomplete_values_atomically(self):
        initial=m.Measurement.objects.count()
        for data in ({**self.create_data(),'author_person_id':str(self.users[m.Role.ADMIN].person_id)},
                     {**self.create_data(),'values':[{'name':'carbono','value':'NaN','unit':'t'}]}):
            with self.assertRaises(DomainError):self.call(m.Role.TECH,'create_measurement',data=data)
        self.assertEqual(m.Measurement.objects.count(),initial)

    def test_closed_period_blocks_new_measurement(self):
        self.business(m.Role.MANAGER,'close_period',self.period.pk,{'reason':'Cierre'})
        with self.assertRaises(DomainError):self.new_draft()

    def test_online_edit_and_send_reject_stale_revision(self):
        v=self.new_draft();self.business(m.Role.TECH,'edit',v.pk,{**self.values(),'methodology':'Primera edición','expected_revision':1})
        for action,data in [('edit',{**self.values(),'expected_revision':1}),('submit',{'expected_revision':1})]:
            with self.assertRaises(DomainError) as ctx:self.business(m.Role.TECH,action,v.pk,data)
            self.assertEqual(ctx.exception.status,409)
        v.refresh_from_db();self.assertEqual(v.status,'BORRADOR');self.assertEqual(v.methodology,'Primera edición')

    def test_new_sync_persists_receipt_with_two_dates_and_original_author(self):
        result=self.call(m.Role.TECH,'sync',data=self.sync_data())
        receipt=m.SyncReceipt.objects.get(pk=result['receipt_id']);v=receipt.version
        self.assertNotEqual(receipt.captured_at,receipt.received_at);self.assertEqual(v.author_id,self.users[m.Role.TECH].person_id)
        self.assertEqual(v.status,'BORRADOR');self.assertEqual(v.edit_revision,1)

    def test_sync_retry_and_changed_payload(self):
        op=uuid.uuid4();data=self.sync_data();a=self.call(m.Role.TECH,'sync',data=data,op=op)
        b=self.call(m.Role.TECH,'sync',data=data,op=op);self.assertEqual(a,b);self.assertEqual(m.SyncReceipt.objects.count(),1)
        with self.assertRaises(DomainError) as ctx:self.call(m.Role.TECH,'sync',data={**data,'methodology':'Distinta'},op=op)
        self.assertEqual(ctx.exception.rule,'IDEMPOTENCIA')

    def test_sync_confirmed_receipt_retrievable_after_period_closes(self):
        op=uuid.uuid4();data=self.sync_data();a=self.call(m.Role.TECH,'sync',data=data,op=op)
        self.business(m.Role.MANAGER,'close_period',self.period.pk,{'reason':'Cerrar'})
        self.assertEqual(self.call(m.Role.TECH,'sync',data=data,op=op),a)

    def test_sync_retry_revalidates_assignment_and_account(self):
        op=uuid.uuid4();data=self.sync_data();self.call(m.Role.TECH,'sync',data=data,op=op)
        assignment=m.FarmAssignment.objects.get(farm=self.farm);self.call(m.Role.SUPERVISOR,'revoke_tech',assignment.pk,{'reason':'Terminó'})
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'sync',data=data,op=op)
        m.Account.objects.filter(pk=self.users[m.Role.TECH].pk).update(is_active=False)
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'sync',data=data)

    def test_sync_author_cannot_be_spoofed(self):
        data={**self.sync_data(),'author_person_id':str(self.users[m.Role.REVIEWER].person_id)}
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'sync',data=data)
        self.assertEqual(m.SyncReceipt.objects.count(),0)

    def test_sync_shared_person_second_account_same_receipt(self):
        other=m.Account.objects.create_user(username='other-tech',person=self.users[m.Role.TECH].person,password=secrets.token_urlsafe(20))
        op=uuid.uuid4();data=self.sync_data();first=self.call(m.Role.TECH,'sync',data=data,op=op)
        self.assertEqual(c.execute(other.pk,'sync','new',data,op),first)

    def test_sync_stale_base_preserves_server_version(self):
        v=self.new_draft();self.business(m.Role.TECH,'edit',v.pk,{**self.values(),'methodology':'Cambio online'})
        data={**self.sync_data(),'version_id':str(v.pk),'base_revision':1}
        with self.assertRaises(DomainError) as ctx:self.call(m.Role.TECH,'sync',data=data)
        self.assertEqual(ctx.exception.status,409);v.refresh_from_db();self.assertEqual(v.methodology,'Cambio online')

    def test_sync_sent_version_is_not_overwritten(self):
        data={**self.sync_data(),'version_id':str(self.version.pk),'base_revision':self.version.edit_revision}
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'sync',data=data)
        self.version.refresh_from_db();self.assertEqual(self.version.status,'ENVIADA')

    def test_sync_closed_period_rejects_new_draft(self):
        self.business(m.Role.MANAGER,'close_period',self.period.pk,{'reason':'Cierre'})
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'sync',data=self.sync_data())
        self.assertEqual(m.SyncReceipt.objects.count(),0)

    def test_sync_authorized_correction_in_closed_period(self):
        self.business(m.Role.REVIEWER,'return',self.version.pk,{'reason':'Corrección'})
        self.business(m.Role.MANAGER,'close_period',self.period.pk,{'reason':'Cierre'})
        am=self.business(m.Role.TECH,'request_amendment',self.version.pk,{'reason':'Ajuste'})
        self.business(m.Role.ADMIN,'authorize_amendment',am['amendment_id'],{'reason':'Autorizada','technician_id':str(self.users[m.Role.TECH].person_id)})
        v=self.business(m.Role.TECH,'correct',self.version.pk,{'amendment_id':am['amendment_id']})
        result=self.call(m.Role.TECH,'sync',data={**self.sync_data(),'version_id':v['version_id'],'base_revision':1})
        self.assertEqual(result['edit_revision'],2);self.period.refresh_from_db();self.assertEqual(self.period.status,'CERRADA')

    def test_sync_wrong_farm_or_period_rejected(self):
        v=self.new_draft()
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'sync',data={**self.sync_data(),'version_id':str(v.pk),'base_revision':1,'farm_id':str(uuid.uuid4())})

    def test_sync_bad_capture_timestamp_rolls_back_measurement(self):
        count=m.Measurement.objects.count()
        with self.assertRaises(DomainError):self.call(m.Role.TECH,'sync',data={**self.sync_data(),'captured_at':'2026-11-10T10:00:00'})
        self.assertEqual(m.Measurement.objects.count(),count)

    def test_sync_event_failure_rolls_back_everything(self):
        before=m.Measurement.objects.count();original=c.event
        def fail(actor,action,*args,**kwargs):
            if action=='BORRADOR_SINCRONIZADO':raise RuntimeError('Evento fallido')
            return original(actor,action,*args,**kwargs)
        with patch('gestion.capture.event',side_effect=fail),self.assertRaises(RuntimeError):self.call(m.Role.TECH,'sync',data=self.sync_data())
        self.assertEqual(m.Measurement.objects.count(),before);self.assertEqual(m.SyncReceipt.objects.count(),0)

    def test_sync_receipt_is_append_only(self):
        result=self.call(m.Role.TECH,'sync',data=self.sync_data())
        with self.assertRaises(DatabaseError),transaction.atomic():m.SyncReceipt.objects.filter(pk=result['receipt_id']).update(base_revision=99)
        with self.assertRaises(DatabaseError),transaction.atomic():m.SyncReceipt.objects.filter(pk=result['receipt_id']).delete()

    def test_queue_status_only_metadata_and_allowed_roles(self):
        self.call(m.Role.TECH,'queue_status',data={'device_id':str(uuid.uuid4()),'pending':2,'conflicts':1})
        for role in (*c.MANAGERS,m.Role.TECH):
            result=c.queue_status(self.users[role].pk);self.assertEqual(result['queues'][0]['pending'],2)
            self.assertNotIn('values',json.dumps(result))
        for role in (m.Role.MANAGER,m.Role.SECURITY,m.Role.OWNER,m.Role.AUDITOR,m.Role.REVIEWER):
            with self.assertRaises(DomainError):c.queue_status(self.users[role].pk)

    def test_bootstrap_minimal_and_role_restricted(self):
        self.new_draft();data=c.bootstrap(self.users[m.Role.TECH].pk)
        self.assertEqual(len(data['versions']),1)
        for forbidden in ('PRIVATE_CONTACT_TEST','PERSONAL_OWNER_TEST','price','password','polygon'):
            self.assertNotIn(forbidden,json.dumps(data))
        for role in m.Role.values:
            if role!=m.Role.TECH:
                with self.assertRaises(DomainError):c.bootstrap(self.users[role].pk)

    def test_api_requires_session_csrf_and_denies_spoof(self):
        path='/api/capture/action/create_measurement/new/'
        self.assertEqual(Client().post(path,data='{}',content_type='application/json').status_code,401)
        client=self.login_client(m.Role.TECH,csrf=True)
        self.assertEqual(client.post(path,data=json.dumps(self.create_data()),content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())).status_code,403)
        boot=client.get('/api/capture/bootstrap/').json()
        response=client.post(path,data=json.dumps(self.create_data()),content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),HTTP_X_CSRFTOKEN=boot['csrf_token'])
        self.assertEqual(response.status_code,200)

    def test_malformed_uuid_is_controlled_and_denial_logged(self):
        response=self.login_client(m.Role.ADMIN).post('/api/capture/action/edit_farm/invalid/',data='{}',content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,400);self.assertTrue(m.Event.objects.filter(action='CAPTURA_DENEGADA').exists())

    def test_public_shell_contains_no_identity_token_or_private_content(self):
        for client in (Client(),self.login_client(m.Role.TECH)):
            response=client.get('/campo/');self.assertEqual(response.status_code,200)
            for secret in ('csrfmiddlewaretoken','TEST-TECNICO','PRIVATE_CONTACT_TEST','sessionid'):self.assertNotIn(secret,response.content.decode())
        sw=Client().get('/campo/sw.js').content.decode();self.assertIn("!PUBLIC.includes(u.pathname)",sw)

    def test_new_pages_render_and_deny_wrong_roles(self):
        for role,paths in [(m.Role.ADMIN,['/farms/','/farms/new/','/owners/','/assignments/','/queues/']),
                           (m.Role.TECH,['/farms/','/measurements/new/','/assignments/','/queues/']),
                           (m.Role.OWNER,['/farms/','/owners/']), (m.Role.SUPERVISOR,['/assignments/','/queues/'])]:
            for path in paths:self.assertEqual(self.login_client(role).get(path).status_code,200,(role,path))
        self.assertEqual(self.login_client(m.Role.TECH).get('/owners/').status_code,403)
        self.assertEqual(self.login_client(m.Role.SUPERVISOR).get('/farms/new/').status_code,403)

    def test_structured_measurement_form_creates_real_draft(self):
        client=self.login_client(m.Role.TECH)
        payload={**self.create_data(),'request_id':str(uuid.uuid4()),'value_name':['carbono_reportado'],
                 'value_number':['121.00'],'value_unit':['tCO2e']};payload.pop('values')
        response=client.post('/measurements/new/',payload)
        self.assertEqual(response.status_code,302);self.assertTrue(m.Version.objects.filter(values=[{'name':'carbono_reportado','value':'121.00','unit':'tCO2e'}]).exists())

    def test_owner_measurement_download_excludes_certificate_price_and_foreign_data(self):
        response=self.login_client(m.Role.OWNER).get(f'/measurements/{self.measurement.pk}/download/')
        self.assertEqual(response.status_code,200);self.assertNotIn('certificates',response.json());self.assertNotIn('owner',response.json())
        self.assertEqual(self.login_client(m.Role.TECH).get(f'/measurements/{self.measurement.pk}/download/').status_code,403)


class CaptureConcurrencyTests(TransactionTestCase):
    def setUp(self):self.users,self.password,self.farm,self.period,self.measurement,self.version=fixture()
    def payload(self):return {'farm_id':str(self.farm.pk),'period_id':str(self.period.pk),'author_person_id':str(self.users[m.Role.TECH].person_id),
          'version_id':None,'base_revision':0,'captured_at':'2026-11-10T12:00:00Z','measured_at':'2026-11-10','methodology':'Concurrente',
          'values':[{'name':'carbono','value':'120.00','unit':'tCO2e'}]}
    def worker(self,op,data):
        close_old_connections()
        try:return ('OK',c.execute(self.users[m.Role.TECH].pk,'sync','new',data,op))
        except DomainError as e:return ('DENIED',e.rule)
        finally:close_old_connections()
    def test_identical_concurrent_sync_creates_one_measurement_and_receipt(self):
        op=uuid.uuid4();before=m.Measurement.objects.count()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.worker(op,self.payload()),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],'OK');self.assertEqual(m.Measurement.objects.count(),before+1);self.assertEqual(m.SyncReceipt.objects.count(),1)
    def test_two_updates_same_base_only_one_wins(self):
        result=c.execute(self.users[m.Role.TECH].pk,'sync','new',self.payload(),uuid.uuid4())
        payload={**self.payload(),'version_id':result['version_id'],'base_revision':1}
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda i:self.worker(uuid.uuid4(),{**payload,'methodology':f'Edición {i}'}),range(2)))
        self.assertEqual(sorted(r[0] for r in results),['DENIED','OK']);self.assertEqual(m.Version.objects.get(pk=result['version_id']).edit_revision,2)
