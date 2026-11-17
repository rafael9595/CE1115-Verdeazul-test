import pyotp
from .identity_helpers import session_for, factor
import copy
import json
import os
import secrets
import tempfile
from pathlib import Path
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction, DatabaseError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.utils import timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from certificados import verify_certificate, fingerprint
from certificados.demo import sample_payload
from gestion import models as m, services as s, queries as q
from gestion.policy import DomainError


def fixture():
    password=secrets.token_urlsafe(20); password_hash=make_password(password)
    users={}
    for role in m.Role.values:
        person=m.Person.objects.create(work_id='TEST-'+role,role=role)
        users[role]=m.Account.objects.create(username=role.lower(),password=password_hash,person=person)
    other=m.Person.objects.create(work_id='TEST-OTHER',role=m.Role.REVIEWER)
    users['OTHER']=m.Account.objects.create(username='other',password=password_hash,person=other)
    owner=m.Owner.objects.create(name='PERSONAL_OWNER_TEST',contact='PRIVATE_CONTACT_TEST')
    m.OwnerLink.objects.create(person=users[m.Role.OWNER].person,owner=owner)
    farm=m.Farm.objects.create(registry_number='TEST-001',name='Finca sintética',area_ha='10.5',owner=owner,
                              polygon=sample_payload()['farm']['polygon_wgs84'])
    period=m.Period.objects.create(name='Prueba')
    measurement=m.Measurement.objects.create(farm=farm,period=period,technician=users[m.Role.TECH].person)
    m.FarmAssignment.objects.create(farm=farm,technician=measurement.technician)
    for reviewer in (users[m.Role.REVIEWER],users['OTHER']):
        m.ReviewAssignment.objects.create(measurement=measurement,reviewer=reviewer.person)
    m.AuditorGrant.objects.create(auditor=users[m.Role.AUDITOR].person,farm=farm,assignment_name='Encargo',
                                 ends=timezone.now()+timedelta(days=1))
    version=m.Version.objects.create(measurement=measurement,number=1,author=measurement.technician,status='ENVIADA',
        measured_at=timezone.localdate(),methodology='Prueba sintética',values=sample_payload()['measurement']['values'],
        submitted_at=timezone.now())
    return users,password,farm,period,measurement,version


class IntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users,cls.password,cls.farm,cls.period,cls.measurement,cls.version=fixture()

    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        pem=self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption()).decode()
        env=patch.dict(os.environ,{'VERDEAZUL_SIGNING_PRIVATE_KEY_PEM':pem,'VERDEAZUL_SIGNING_PRIVATE_KEY_FILE':''})
        env.start(); self.addCleanup(env.stop)

    def call(self,role,action,target=None,data=None,op=None,recent=True):
        if action in ('edit','submit'):
            data={**(data or {}),'expected_revision':m.Version.objects.get(pk=target or self.version.pk).edit_revision}
        return s.execute(self.users[role].pk,action,str(target or self.version.pk),data or {},op or uuid.uuid4(),
                         timezone.now() if recent else timezone.now()-timedelta(minutes=6))

    def approve(self):
        response=self.call(m.Role.REVIEWER,'approve')
        return m.Certificate.objects.get(pk=response['certificate_id'])

    def login(self,role,csrf=False):
        return session_for(self.users[role],csrf=csrf)

    def test_approve_persists_signed_bytes_review_and_events(self):
        cert=self.approve()
        self.assertTrue(verify_certificate(bytes(cert.signed_bytes),[fingerprint(self.key.public_key())]).accepted)
        self.version.refresh_from_db(); self.assertEqual(self.version.status,'APROBADA')
        self.assertEqual(m.Review.objects.count(),1)
        self.assertEqual(m.Event.objects.filter(action='CERTIFICADO_EMITIDO').count(),1)

    def test_altered_persisted_document_fails_verification(self):
        cert=self.approve(); doc=json.loads(bytes(cert.signed_bytes))
        doc['payload']['measurement']['values'][0]['value']='9999.00'
        self.assertFalse(verify_certificate(json.dumps(doc).encode(),[fingerprint(self.key.public_key())]).accepted)

    def test_all_other_roles_cannot_approve(self):
        for role in m.Role.values:
            if role==m.Role.REVIEWER: continue
            with self.subTest(role=role),self.assertRaises(DomainError): self.call(role,'approve')
        self.assertEqual(m.Certificate.objects.count(),0)

    def test_unassigned_reviewer_cannot_approve(self):
        m.ReviewAssignment.objects.filter(reviewer=self.users[m.Role.REVIEWER].person).update(ends=timezone.now())
        with self.assertRaises(DomainError): self.approve()

    def test_historical_author_cannot_review_after_role_change(self):
        person=self.users[m.Role.TECH].person
        m.Person.objects.filter(pk=person.pk).update(role=m.Role.REVIEWER)
        m.ReviewAssignment.objects.create(measurement=self.measurement,reviewer=person)
        with self.assertRaises(DomainError) as ctx: self.call(m.Role.TECH,'approve')
        self.assertEqual(ctx.exception.rule,'C3')

    def test_duplicate_account_same_person_cannot_bypass_history(self):
        person=self.users[m.Role.TECH].person
        m.Person.objects.filter(pk=person.pk).update(role=m.Role.REVIEWER)
        other=m.Account.objects.create_user(username='sameperson',person=person,password=secrets.token_urlsafe(20))
        m.ReviewAssignment.objects.create(measurement=self.measurement,reviewer=person)
        with self.assertRaises(DomainError): s.execute(other.pk,'approve',self.version.pk,{},uuid.uuid4())

    def test_identical_operation_returns_same_certificate(self):
        op=uuid.uuid4(); a=self.call(m.Role.REVIEWER,'approve',op=op); b=self.call(m.Role.REVIEWER,'approve',op=op)
        self.assertEqual(a,b); self.assertEqual(m.Certificate.objects.count(),1)
        self.assertEqual(m.Event.objects.filter(action='CERTIFICADO_EMITIDO').count(),1)

    def test_idempotency_reuse_with_different_content_rejected(self):
        op=uuid.uuid4(); self.call(m.Role.REVIEWER,'approve',op=op)
        with self.assertRaises(DomainError) as ctx: self.call(m.Role.REVIEWER,'approve',data={'extra':'value'},op=op)
        self.assertEqual(ctx.exception.rule,'IDEMPOTENCIA')

    def test_retry_rechecks_current_authorization(self):
        op=uuid.uuid4(); self.call(m.Role.REVIEWER,'approve',op=op)
        m.ReviewAssignment.objects.filter(reviewer=self.users[m.Role.REVIEWER].person).update(ends=timezone.now())
        with self.assertRaises(DomainError): self.call(m.Role.REVIEWER,'approve',op=op)

    def test_failed_signing_rolls_back_approval_and_version(self):
        with patch.dict(os.environ,{'VERDEAZUL_SIGNING_PRIVATE_KEY_PEM':'invalid'}):
            with self.assertRaises(DomainError): self.approve()
        self.assertEqual(m.Certificate.objects.count(),0); self.assertEqual(m.Review.objects.count(),0)
        self.version.refresh_from_db(); self.assertEqual(self.version.status,'ENVIADA')
        self.assertTrue(m.Event.objects.filter(result='DENEGADO').exists())

    def test_failed_audit_rolls_back_certificate(self):
        original=s.event
        def fail(actor,action,*args,**kwargs):
            if action=='CERTIFICADO_EMITIDO': raise RuntimeError('Fallo simulado de auditoría')
            return original(actor,action,*args,**kwargs)
        with patch('gestion.services.event',side_effect=fail),self.assertRaises(RuntimeError): self.approve()
        self.assertEqual(m.Certificate.objects.count(),0); self.assertEqual(m.Review.objects.count(),0)
        self.version.refresh_from_db(); self.assertEqual(self.version.status,'ENVIADA')

    def test_return_requires_reason(self):
        with self.assertRaises(DomainError): self.call(m.Role.REVIEWER,'return',data={'reason':''})

    def test_return_and_correction_preserve_original_version(self):
        self.call(m.Role.REVIEWER,'return',data={'reason':'Revisar valor'})
        result=self.call(m.Role.TECH,'correct')
        new=m.Version.objects.get(pk=result['version_id'])
        self.assertEqual(new.source_id,self.version.pk); self.assertEqual(new.author_id,self.version.author_id)
        self.version.refresh_from_db(); self.assertEqual(self.version.status,'DEVUELTA')

    def test_closed_period_blocks_ordinary_correction(self):
        self.call(m.Role.REVIEWER,'return',data={'reason':'Corregir'})
        self.call(m.Role.MANAGER,'close_period',target=self.period.pk,data={'reason':'Cierre'})
        with self.assertRaises(DomainError): self.call(m.Role.TECH,'correct')

    def test_closed_period_amendment_replacement_full_flow(self):
        cert=self.approve(); original=bytes(cert.signed_bytes)
        self.call(m.Role.MANAGER,'close_period',self.period.pk,{'reason':'Fin del período'})
        am=self.call(m.Role.OWNER,'request_amendment',data={'reason':'Corregir dato'})
        self.call(m.Role.ADMIN,'authorize_amendment',am['amendment_id'],
                  {'reason':'Corrección aprobada','technician_id':str(self.version.author_id)})
        corrected=self.call(m.Role.TECH,'correct',data={'amendment_id':am['amendment_id']})['version_id']
        self.call(m.Role.TECH,'edit',corrected,{'measured_at':timezone.localdate().isoformat(),
                 'methodology':'Corrección revisable','values':[{'name':'carbono_reportado','value':'120.00','unit':'tCO2e'}]})
        self.call(m.Role.TECH,'submit',corrected)
        with self.assertRaises(DomainError): self.call(m.Role.REVIEWER,'approve',corrected)
        self.call(m.Role.ADMIN,'invalidate',cert.pk,{'reason':'Se reemplaza por corrección'})
        next_id=self.call(m.Role.REVIEWER,'approve',corrected)['certificate_id']
        new=m.Certificate.objects.get(pk=next_id)
        self.assertEqual(new.predecessor_id,cert.pk)
        self.period.refresh_from_db(); self.assertEqual(self.period.status,'CERRADA')
        cert.refresh_from_db(); self.assertEqual(bytes(cert.signed_bytes),original)
        self.assertEqual(m.Certificate.objects.filter(status='VIGENTE').count(),1)
        report=q.report(self.users[m.Role.ADMIN].pk,self.measurement.pk)
        self.assertEqual(report['certificates'][0]['invalidation']['reason'],'Se reemplaza por corrección')
        self.assertEqual(report['amendments'][0]['authorization_reason'],'Corrección aprobada')

    def test_amendment_authorization_does_not_approve(self):
        self.call(m.Role.REVIEWER,'return',data={'reason':'Corregir'})
        am=self.call(m.Role.TECH,'request_amendment',data={'reason':'Necesita ajuste'})
        self.call(m.Role.ADMIN,'authorize_amendment',am['amendment_id'],
                  {'reason':'Autorizar corrección','technician_id':str(self.version.author_id)})
        self.assertEqual(m.Certificate.objects.count(),0)

    def test_manager_cannot_authorize_amendment_or_invalidate(self):
        cert=self.approve(); am=self.call(m.Role.MANAGER,'request_amendment',data={'reason':'Revisar'})
        for action,target,data in [('authorize_amendment',am['amendment_id'],{'reason':'x','technician_id':str(self.version.author_id)}),
                                   ('invalidate',cert.pk,{'reason':'x'})]:
            with self.assertRaises(DomainError): self.call(m.Role.MANAGER,action,target,data)

    def test_admin_sensitive_operation_requires_recent_authentication(self):
        cert=self.approve()
        with self.assertRaises(DomainError) as ctx: self.call(m.Role.ADMIN,'invalidate',cert.pk,{'reason':'x'},recent=False)
        self.assertEqual(ctx.exception.rule,'REAUTH')

    def test_invalidation_preserves_signature_and_bytes(self):
        cert=self.approve(); original=bytes(cert.signed_bytes)
        self.call(m.Role.ADMIN,'invalidate',cert.pk,{'reason':'Motivo documentado'})
        cert.refresh_from_db(); self.assertEqual(cert.status,'INVALIDADO'); self.assertEqual(bytes(cert.signed_bytes),original)
        self.assertTrue(verify_certificate(original,[fingerprint(self.key.public_key())]).accepted)

    def test_certificate_and_review_database_immutability(self):
        cert=self.approve()
        for update in (lambda:m.Certificate.objects.filter(pk=cert.pk).update(signed_bytes=b'altered'),
                       lambda:m.Review.objects.filter(pk=cert.review_id).update(reason='altered'),
                       lambda:m.Version.objects.filter(pk=self.version.pk).update(values=[]),
                       lambda:m.Event.objects.all().update(result='FALSO')):
            with self.subTest(update=update),self.assertRaises(DatabaseError),transaction.atomic(): update()

    def test_physical_evidence_deletion_is_denied(self):
        cert=self.approve()
        with self.assertRaises(DatabaseError),transaction.atomic():
            with connection.cursor() as c: c.execute('DELETE FROM gestion_certificate WHERE id=%s',[cert.pk])

    def test_database_unique_current_certificate_even_across_periods(self):
        cert=self.approve()
        p=m.Period.objects.create(name='Otro período')
        measurement=m.Measurement.objects.create(farm=self.farm,period=p,technician=self.version.author)
        ver=m.Version.objects.create(measurement=measurement,number=1,author=self.version.author,status='APROBADA',
                                     measured_at=timezone.localdate(),methodology='Prueba',values=self.version.values)
        review=m.Review.objects.create(version=ver,reviewer=self.users[m.Role.REVIEWER].person,decision='APROBADA')
        with self.assertRaises(DatabaseError),transaction.atomic():
            m.Certificate.objects.create(farm=self.farm,review=review,signed_bytes=bytes(cert.signed_bytes),key_id=cert.key_id)

    def test_invalid_geography_prevents_approval(self):
        for polygon in ([['0','0'],['1','0'],['1','1'],['0','0']],
                        [['-84','10'],['-83.999','10.001'],['-84','10.001'],['-83.999','10'],['-84','10']]):
            m.Farm.objects.filter(pk=self.farm.pk).update(polygon=polygon)
            with self.assertRaises(DomainError): self.approve()
        self.assertEqual(m.Review.objects.count(),0)

    def test_admin_cannot_modify_approved_values(self):
        self.approve()
        with self.assertRaises(DomainError): self.call(m.Role.ADMIN,'edit',data={'values':[]})

    def test_technician_cannot_edit_submitted_values(self):
        with self.assertRaises(DomainError): self.call(m.Role.TECH,'edit',data={'values':[]})

    def test_unavailable_original_technician_blocks_authorization(self):
        self.approve(); am=self.call(m.Role.ADMIN,'request_amendment',data={'reason':'Revisar'})
        m.Account.objects.filter(person=self.version.author).update(is_active=False)
        with self.assertRaises(DomainError): self.call(m.Role.ADMIN,'authorize_amendment',am['amendment_id'],
                                {'reason':'x','technician_id':str(self.version.author_id)})

    def test_price_permissions_and_filtered_reports(self):
        cert=self.approve(); self.call(m.Role.MANAGER,'set_price',cert.pk,{'amount':'12345.67','currency':'USD'})
        for role in (m.Role.TECH,m.Role.REVIEWER,m.Role.SUPERVISOR,m.Role.AUDITOR,m.Role.SECURITY):
            with self.subTest(role=role),self.assertRaises(DomainError): q.read_price(self.users[role].pk,cert.pk)
        for role in (m.Role.TECH,m.Role.REVIEWER,m.Role.SUPERVISOR,m.Role.AUDITOR):
            data=q.report(self.users[role].pk,self.measurement.pk); raw=json.dumps(data)
            self.assertNotIn('12345.67',raw); self.assertNotIn('PRIVATE_CONTACT_TEST',raw); self.assertNotIn('PERSONAL_OWNER_TEST',raw)
        self.assertIn('12345.67',json.dumps(q.report(self.users[m.Role.MANAGER].pk,self.measurement.pk)))
        self.assertNotIn('PRIVATE_CONTACT_TEST',json.dumps(q.report(self.users[m.Role.MANAGER].pk,self.measurement.pk)))
        self.assertIn('PRIVATE_CONTACT_TEST',json.dumps(q.report(self.users[m.Role.OWNER].pk,self.measurement.pk)))

    def test_auditor_expired_assignment_denied(self):
        m.AuditorGrant.objects.all().update(ends=timezone.now())
        with self.assertRaises(DomainError): q.report(self.users[m.Role.AUDITOR].pk,self.measurement.pk)

    def test_foreign_owner_denied(self):
        cert=self.approve(); m.OwnerLink.objects.all().update(ends=timezone.now())
        with self.assertRaises(DomainError): q.download_certificate(self.users[m.Role.OWNER].pk,cert.pk)

    def test_o8_download_matrix(self):
        cert=self.approve()
        for role in (m.Role.TECH,m.Role.REVIEWER,m.Role.ADMIN,m.Role.OWNER,m.Role.MANAGER):
            self.assertEqual(q.download_certificate(self.users[role].pk,cert.pk),bytes(cert.signed_bytes))
        for role in (m.Role.AUDITOR,m.Role.SUPERVISOR,m.Role.SECURITY):
            with self.subTest(role=role),self.assertRaises(DomainError): q.download_certificate(self.users[role].pk,cert.pk)

    def test_historical_access_does_not_grant_future_measurements(self):
        self.approve(); m.FarmAssignment.objects.all().update(ends=timezone.now())
        q.report(self.users[m.Role.TECH].pk,self.measurement.pk)
        next_measurement=m.Measurement.objects.create(farm=self.farm,period=self.period,technician=self.users['OTHER'].person)
        with self.assertRaises(DomainError): q.report(self.users[m.Role.TECH].pk,next_measurement.pk)

    def test_farm_change_does_not_change_original_certificate(self):
        cert=self.approve(); original=bytes(cert.signed_bytes)
        m.Farm.objects.filter(pk=self.farm.pk).update(name='Nombre nuevo')
        self.assertEqual(q.download_certificate(self.users[m.Role.ADMIN].pk,cert.pk),original)

    def test_periods_role_permissions_and_no_reopening(self):
        for role in (m.Role.TECH,m.Role.REVIEWER,m.Role.SUPERVISOR,m.Role.OWNER,m.Role.AUDITOR,m.Role.SECURITY):
            with self.assertRaises(DomainError): self.call(role,'open_period','new',{'name':'Nuevo'})
        self.call(m.Role.MANAGER,'close_period',self.period.pk,{'reason':'Fin'})
        with self.assertRaises(DatabaseError),transaction.atomic():
            m.Period.objects.filter(pk=self.period.pk).update(status='ABIERTA')

    def test_security_audit_contains_metadata_only(self):
        self.approve(); raw=json.dumps(q.audit(self.users[m.Role.SECURITY].pk))
        self.assertNotIn('125.50',raw); self.assertNotIn('PRIVATE_CONTACT_TEST',raw)

    def test_unauthenticated_api_denied(self):
        response=Client().post(f'/api/action/approve/{self.version.pk}/',data='{}',content_type='application/json')
        self.assertEqual(response.status_code,401)

    def test_csrf_is_required(self):
        client=self.login(m.Role.REVIEWER,csrf=True)
        response=client.post(f'/api/action/approve/{self.version.pk}/',data='{}',content_type='application/json',
                             HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,403)

    def test_browser_role_or_reauth_spoof_does_not_authorize(self):
        client=self.login(m.Role.TECH)
        response=client.post(f'/api/action/approve/{self.version.pk}/',data=json.dumps({'role':'VERIFICADOR','authenticated_at':'now'}),
                             content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,403)

    def test_api_approval_then_download_then_verify(self):
        client=self.login(m.Role.REVIEWER)
        response=client.post(f'/api/action/approve/{self.version.pk}/',data='{}',content_type='application/json',
                             HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,200,response.content)
        cert_id=response.json()['certificate_id']; download=client.get(f'/api/certificates/{cert_id}/download/')
        self.assertTrue(verify_certificate(download.content,[fingerprint(self.key.public_key())]).accepted)

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(DomainError): self.call(m.Role.REVIEWER,'approve',data={'price':'100'})

    def test_role_change_revokes_open_session(self):
        client=self.login(m.Role.TECH)
        m.Person.objects.filter(pk=self.users[m.Role.TECH].person_id).update(role=m.Role.REVIEWER)
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_disabled_account_is_denied(self):
        client=self.login(m.Role.REVIEWER)
        m.Account.objects.filter(pk=self.users[m.Role.REVIEWER].pk).update(is_active=False)
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_expired_session_is_denied(self):
        client=self.login(m.Role.REVIEWER); session=client.session
        session['last_activity']=timezone.now().timestamp()-1801; session.save()
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_dashboard_renders_all_roles_without_private_leak(self):
        self.approve()
        for role in m.Role.values:
            response=self.login(role).get('/')
            self.assertEqual(response.status_code,200,response.content[:300])
            if role not in (m.Role.ADMIN,m.Role.OWNER): self.assertNotContains(response,'PRIVATE_CONTACT_TEST')

    def test_password_login_sets_server_session_and_requires_csrf(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/login/',{'username':'verificador','password':self.password}).status_code,403)
        client.get('/login/')
        response=client.post('/login/',{'username':'verificador','password':self.password},
                             HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,302)
        self.assertNotIn('reauth_at',client.session)
        self.assertEqual(client.get('/api/workspace/').status_code,401)
        secret=factor(self.users[m.Role.REVIEWER])
        client.post('/identity/mfa/',{'code':pyotp.TOTP(secret).now()},HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertIn('reauth_at',client.session)
        self.assertEqual(client.get('/api/workspace/').status_code,200)

    def test_ten_failed_logins_temporarily_block_correct_password(self):
        client=Client()
        for _ in range(10): client.post('/login/',{'username':'verificador','password':'incorrecta'})
        client.post('/login/',{'username':'verificador','password':self.password})
        self.assertEqual(client.get('/api/workspace/').status_code,401)
        self.assertEqual(m.Event.objects.filter(action='AUTENTICACION_FALLIDA').count(),10)

    def test_reauthentication_unlocks_sensitive_action(self):
        cert=self.approve(); client=self.login(m.Role.ADMIN)
        session=client.session; session['reauth_at']=timezone.now().timestamp()-301; session.save()
        path=f'/api/action/invalidate/{cert.pk}/'
        response=client.post(path,data=json.dumps({'reason':'Corrección'}),content_type='application/json',
                             HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,403)
        self.assertEqual(client.post('/reauth/',{'password':self.password,'code':pyotp.TOTP(factor(self.users[m.Role.ADMIN])).now()}).status_code,302)
        response=client.post(path,data=json.dumps({'reason':'Corrección'}),content_type='application/json',
                             HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,200)

    def test_reauthentication_is_rate_limited(self):
        client=self.login(m.Role.ADMIN)
        for _ in range(10): self.assertEqual(client.post('/reauth/',{'password':'incorrecta'}).status_code,403)
        self.assertEqual(client.post('/reauth/',{'password':self.password,'code':pyotp.TOTP(factor(self.users[m.Role.ADMIN])).now()}).status_code,403)

    def test_uploaded_original_and_altered_file_have_different_results(self):
        cert=self.approve(); original=bytes(cert.signed_bytes)
        altered=json.loads(original); altered['payload']['measurement']['values'][0]['value']='9999.00'
        with tempfile.TemporaryDirectory() as folder:
            public=Path(folder)/'public.pem'
            public.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM,
                                                                  serialization.PublicFormat.SubjectPublicKeyInfo))
            with override_settings(TRUSTED_PUBLIC_KEY_FILES=[str(public)]):
                for data,accepted in [(original,True),(json.dumps(altered).encode(),False)]:
                    response=Client().post('/verify/',{'certificate':SimpleUploadedFile('cert.json',data)})
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.context['result'].accepted,accepted)

    def test_invalid_object_identifier_is_controlled_and_audited(self):
        client=self.login(m.Role.REVIEWER)
        response=client.post('/api/action/approve/not-a-uuid/',data='{}',content_type='application/json',
                             HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,404)
        self.assertTrue(m.Event.objects.filter(result='DENEGADO',rule='OBJETO').exists())


class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.users,self.password,self.farm,self.period,self.measurement,self.version=fixture()
        key=Ed25519PrivateKey.generate()
        pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
        env=patch.dict(os.environ,{'VERDEAZUL_SIGNING_PRIVATE_KEY_PEM':pem,'VERDEAZUL_SIGNING_PRIVATE_KEY_FILE':''})
        env.start(); self.addCleanup(env.stop)

    def worker(self,user_id,request_id):
        close_old_connections()
        try:
            return ('OK',s.execute(user_id,'approve',self.version.pk,{},request_id))
        except DomainError as e: return ('DENIED',e.rule)
        finally: close_old_connections()

    def test_two_reviewers_concurrently_only_one_certificate(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda p:self.worker(*p),[
                (self.users[m.Role.REVIEWER].pk,uuid.uuid4()),(self.users['OTHER'].pk,uuid.uuid4())]))
        self.assertEqual(sorted(x[0] for x in results),['DENIED','OK'])
        self.assertEqual(m.Certificate.objects.filter(status='VIGENTE').count(),1)
        self.assertEqual(m.Review.objects.count(),1)

    def test_identical_concurrent_retry_returns_same_result(self):
        request_id=uuid.uuid4(); user_id=self.users[m.Role.REVIEWER].pk
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.worker(user_id,request_id),range(2)))
        self.assertEqual(results[0],results[1]); self.assertEqual(results[0][0],'OK')
        self.assertEqual(m.Certificate.objects.count(),1)
