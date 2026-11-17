import json
import secrets
import tempfile
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import pyotp
from cryptography.fernet import Fernet
from django.db import DatabaseError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.utils import timezone
from gestion import models as m, identity as i, services, capture
from gestion.policy import DomainError, Actor
from .test_integration import fixture
from .identity_helpers import session_for, factor


class IdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users,cls.password,cls.farm,cls.period,cls.measurement,cls.version=fixture()

    def setUp(self):
        self.now=timezone.now()
        clock=patch('django.utils.timezone.now',return_value=self.now);clock.start();self.addCleanup(clock.stop)
        breach=patch('gestion.identity.breach_count',return_value=0);breach.start();self.addCleanup(breach.stop)
        self.admin=session_for(self.users[m.Role.ADMIN])

    def api(self,action,target='new',data=None,client=None):
        return (client or self.admin).post(f'/api/identity/action/{action}/{target}/',
            data=json.dumps(data or {}),content_type='application/json')

    def create(self,role=m.Role.TECH,work='NEW-001',username='new.user',extra=None):
        data={'username':username,'work_id':work,'primary_role':role,'additional_roles':[],
              'first_name':'Prueba','last_name':'Sintética','email':'prueba@example.invalid',
              'reason':'Alta para prueba','verification_reference':'Documento sintético verificado'}
        data.update(extra or {})
        return self.api('create',data=data)

    def otp(self,account):
        return pyotp.TOTP(factor(account)).at(self.now)

    def current(self,role):
        self.users[role].refresh_from_db()
        return self.users[role]

    def roles(self,account,primary,additional=None,client=None,version=None):
        account.refresh_from_db()
        return self.api('roles',account.pk,{'primary_role':primary,'additional_roles':additional or [],
            'expected_version':version if version is not None else account.person.auth_version,'reason':'Cambio de funciones'},client)

    def recover(self,account,reset=False):
        return self.api('recovery',account.pk,{'reason':'Recuperación solicitada','verification_reference':'Verificación presencial sintética','reset_mfa':reset})

    def test_admin_creates_unusable_password_and_hashed_activation(self):
        response=self.create();self.assertEqual(response.status_code,200,response.content)
        result=response.json();account=m.Account.objects.get(pk=result['account_id'])
        self.assertFalse(account.has_usable_password());self.assertTrue(account.must_change_password)
        ticket=m.CredentialTicket.objects.get(account=account)
        self.assertNotEqual(ticket.digest,result['activation_code'])
        self.assertEqual(ticket.digest,i.digest(result['activation_code']))
        self.assertNotIn(result['activation_code'],json.dumps(list(m.Event.objects.values('detail'))))

    def test_each_non_admin_cannot_create_or_list_accounts(self):
        for role in m.Role.values:
            if role==m.Role.ADMIN:continue
            client=session_for(self.users[role])
            self.assertEqual(client.get('/api/identity/accounts/').status_code,403,role)
            self.assertEqual(self.api('create',client=client).status_code,403,role)

    def test_csrf_rejects_account_mutation(self):
        client=session_for(self.users[m.Role.ADMIN],csrf=True)
        self.assertEqual(self.api('create',client=client).status_code,403)

    def test_account_create_requires_recent_auth(self):
        session=self.admin.session;session['reauth_at']=self.now.timestamp()-301;session.save()
        self.assertEqual(self.create().status_code,403)

    def test_duplicate_identity_uses_same_person(self):
        first=self.create().json()
        second=self.create(username='second.user').json()
        self.assertEqual(m.Account.objects.get(pk=first['account_id']).person_id,m.Account.objects.get(pk=second['account_id']).person_id)

    def test_duplicate_identity_cannot_split_incompatible_roles(self):
        self.create()
        self.assertEqual(self.create(role=m.Role.REVIEWER,username='second.user').status_code,409)

    def test_static_role_conflict_rejected_on_creation(self):
        self.assertEqual(self.create(extra={'additional_roles':[m.Role.REVIEWER]}).status_code,403)
        self.assertFalse(m.Account.objects.filter(username='new.user').exists())

    def test_static_role_conflict_rejected_on_change(self):
        self.assertEqual(self.roles(self.users[m.Role.TECH],m.Role.TECH,[m.Role.REVIEWER]).status_code,403)

    def test_database_guard_rejects_incompatible_roles(self):
        with self.assertRaises(DatabaseError),transaction.atomic():
            m.Person.objects.filter(pk=self.users[m.Role.TECH].person_id).update(additional_roles=[m.Role.REVIEWER])

    def test_database_guard_rejects_unknown_role(self):
        with self.assertRaises(DatabaseError),transaction.atomic():
            m.Person.objects.create(work_id='BAD-ROLE',role=m.Role.TECH,additional_roles=['SUPERADMIN'])

    def test_database_guard_prevents_reassigning_account_identity(self):
        with self.assertRaises(DatabaseError),transaction.atomic():
            m.Account.objects.filter(pk=self.users[m.Role.TECH].pk).update(person=self.users[m.Role.REVIEWER].person)

    def test_work_id_is_case_insensitive_and_immutable(self):
        with self.assertRaises(DatabaseError),transaction.atomic():
            m.Person.objects.create(work_id=self.users[m.Role.TECH].person.work_id.lower(),role=m.Role.TECH)
        with self.assertRaises(DatabaseError),transaction.atomic():
            m.Person.objects.filter(pk=self.users[m.Role.TECH].person_id).update(work_id='RENAMED-ID')

    def test_admin_hierarchy_does_not_inherit_technical_roles(self):
        roles=self.users[m.Role.ADMIN].person.effective_roles
        self.assertEqual(roles,{m.Role.ADMIN,m.Role.MANAGER,m.Role.SUPERVISOR,m.Role.SECURITY})

    def test_role_change_revokes_all_accounts_and_ends_assignment(self):
        account=self.users[m.Role.TECH]
        duplicate=m.Account.objects.create_user(username='duplicate',person=account.person,password=self.password)
        c1=session_for(account);c2=session_for(duplicate)
        response=self.roles(account,m.Role.MANAGER)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(c1.get('/api/workspace/').status_code,401)
        self.assertEqual(c2.get('/api/workspace/').status_code,401)
        self.assertFalse(i.live(m.FarmAssignment.objects.filter(technician=account.person)).exists())
        self.assertEqual(m.Version.objects.get(pk=self.version.pk).author_id,account.person_id)

    def test_stale_role_form_does_not_overwrite(self):
        account=self.users[m.Role.TECH];old=account.person.auth_version
        self.assertEqual(self.roles(account,m.Role.MANAGER).status_code,200)
        self.assertEqual(self.roles(account,m.Role.SUPERVISOR,version=old).status_code,409)
        self.assertEqual(self.current(m.Role.TECH).person.role,m.Role.MANAGER)

    def test_historical_author_remains_forbidden_after_role_change(self):
        account=self.users[m.Role.TECH]
        self.assertEqual(self.roles(account,m.Role.REVIEWER).status_code,200)
        m.ReviewAssignment.objects.create(measurement=self.measurement,reviewer=account.person)
        client=session_for(self.current(m.Role.TECH))
        response=client.post(f'/api/action/approve/{self.version.pk}/',data='{}',content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,403);self.assertEqual(response.json()['rule'],'C3')

    def test_additional_role_can_be_selected_without_primary_privilege_bleed(self):
        account=self.users[m.Role.OWNER]
        self.assertEqual(self.roles(account,m.Role.OWNER,[m.Role.MANAGER]).status_code,200)
        client=session_for(self.current(m.Role.OWNER))
        self.assertEqual(client.post('/identity/role/',{'role':m.Role.MANAGER}).status_code,302)
        self.assertEqual(client.get('/api/workspace/').json()['role'],m.Role.MANAGER)
        self.assertEqual(client.get('/api/capture/owners/').status_code,403)
        self.assertEqual(client.get('/api/identity/accounts/').status_code,403)

    def test_role_switch_cannot_select_unassigned_role(self):
        client=session_for(self.users[m.Role.TECH])
        self.assertEqual(client.post('/identity/role/',{'role':m.Role.ADMIN}).status_code,403)
        self.assertEqual(client.get('/api/workspace/').json()['role'],m.Role.TECH)

    def test_additional_technician_is_assignable(self):
        account=self.users[m.Role.OWNER]
        self.assertEqual(self.roles(account,m.Role.OWNER,[m.Role.TECH]).status_code,200)
        data={'person_id':str(account.person_id),'reason':'Asignación de función adicional'}
        response=self.admin.post(f'/api/capture/action/assign_tech/{self.farm.pk}/',data=json.dumps(data),content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,200,response.content)
        client=session_for(self.current(m.Role.OWNER),role=m.Role.TECH)
        self.assertEqual(client.get('/api/capture/bootstrap/').status_code,200)

    def test_disable_all_accounts_preserves_evidence_and_reenable_does_not_restore_assignments(self):
        account=self.users[m.Role.TECH];client=session_for(account)
        second=m.Account.objects.create_user(username='second',person=account.person,password=self.password)
        self.assertEqual(self.api('disable',account.pk,{'reason':'Baja'}).status_code,200)
        second.refresh_from_db();self.assertFalse(second.is_active)
        self.assertEqual(client.get('/api/workspace/').status_code,401)
        self.assertTrue(m.Version.objects.filter(pk=self.version.pk).exists())
        self.assertEqual(self.api('enable',account.pk,{'reason':'Reingreso'}).status_code,200)
        self.assertFalse(i.live(m.FarmAssignment.objects.filter(technician=account.person)).exists())

    def test_last_admin_cannot_be_disabled_or_demoted(self):
        account=self.users[m.Role.ADMIN]
        self.assertEqual(self.api('disable',account.pk,{'reason':'Baja'}).status_code,409)
        self.assertEqual(self.roles(account,m.Role.MANAGER).status_code,409)

    def test_pending_admin_does_not_allow_removing_last_working_admin(self):
        self.assertEqual(self.create(role=m.Role.ADMIN).status_code,200)
        self.assertEqual(self.api('disable',self.users[m.Role.ADMIN].pk,{'reason':'Baja'}).status_code,409)

    def test_configured_second_admin_allows_removing_first(self):
        person=m.Person.objects.create(work_id='SECOND-ADMIN',role=m.Role.ADMIN)
        account=m.Account.objects.create_user(username='second.admin',person=person,password=self.password)
        factor(account)
        self.assertEqual(self.api('disable',self.users[m.Role.ADMIN].pk,{'reason':'Relevo'}).status_code,200)
        self.assertEqual(self.admin.get('/api/workspace/').status_code,401)

    def test_disabled_person_cannot_regain_access_by_new_account(self):
        account=self.users[m.Role.TECH]
        self.api('disable',account.pk,{'reason':'Baja'})
        self.assertEqual(self.create(work=account.person.work_id).status_code,409)

    def test_logout_revokes_before_following_request_and_records_event(self):
        account=self.users[m.Role.TECH];client=session_for(account)
        session=m.AuthSession.objects.get(key_digest=i.digest(client.session.session_key))
        self.assertEqual(client.post('/logout/').status_code,302)
        session.refresh_from_db();self.assertIsNotNone(session.revoked_at)
        self.assertEqual(client.get('/api/workspace/').status_code,401)
        self.assertTrue(m.Event.objects.filter(actor=account.person,action='LOGOUT').exists())

    def test_self_profile_allows_contact_but_not_roles_or_legal_name(self):
        client=session_for(self.users[m.Role.OWNER])
        self.assertEqual(client.post('/identity/profile/',{'email':'new@example.invalid'}).status_code,302)
        self.assertEqual(client.post('/identity/profile/',{'email':'new@example.invalid','role':m.Role.ADMIN}).status_code,400)
        self.assertEqual(client.post('/identity/profile/',{'email':'new@example.invalid','first_name':'Changed'}).status_code,400)

    def test_profile_and_sessions_do_not_expose_secrets(self):
        secret=factor(self.users[m.Role.TECH]);client=session_for(self.users[m.Role.TECH])
        for path in ('/identity/profile/','/api/identity/sessions/'):
            text=client.get(path).content.decode()
            self.assertNotIn(secret,text);self.assertNotIn(self.users[m.Role.TECH].password,text)
            self.assertNotIn(client.session.session_key,text);self.assertNotIn('key_digest',text)

    def test_session_owner_cannot_view_or_revoke_others(self):
        other=session_for(self.users[m.Role.REVIEWER]);client=session_for(self.users[m.Role.TECH])
        rows=client.get('/api/identity/sessions/').json()['sessions']
        self.assertTrue(all(x['work_id']==self.users[m.Role.TECH].person.work_id for x in rows))
        target=m.AuthSession.objects.get(key_digest=i.digest(other.session.session_key))
        self.assertEqual(client.post(f'/api/identity/sessions/{target.pk}/revoke/').status_code,403)

    def test_security_can_read_global_session_metadata_but_not_revoke(self):
        other=session_for(self.users[m.Role.TECH]);client=session_for(self.users[m.Role.SECURITY])
        rows=client.get('/api/identity/sessions/').json()['sessions']
        self.assertGreaterEqual(len(rows),3);self.assertTrue(all(not x['can_revoke'] for x in rows))
        target=m.AuthSession.objects.get(key_digest=i.digest(other.session.session_key))
        self.assertEqual(client.post(f'/api/identity/sessions/{target.pk}/revoke/').status_code,403)
        own=m.AuthSession.objects.get(key_digest=i.digest(client.session.session_key))
        self.assertEqual(client.post(f'/api/identity/sessions/{own.pk}/revoke/').status_code,403)

    def test_admin_revocation_is_enforced_on_next_request(self):
        client=session_for(self.users[m.Role.TECH]);target=m.AuthSession.objects.get(key_digest=i.digest(client.session.session_key))
        self.assertEqual(self.admin.post(f'/api/identity/sessions/{target.pk}/revoke/').status_code,200)
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_owner_can_revoke_second_session_without_revoking_current(self):
        client=session_for(self.users[m.Role.TECH]);other=session_for(self.users[m.Role.TECH])
        target=m.AuthSession.objects.get(key_digest=i.digest(other.session.session_key))
        self.assertEqual(client.post(f'/api/identity/sessions/{target.pk}/revoke/').status_code,200)
        self.assertEqual(other.get('/api/workspace/').status_code,401)
        self.assertEqual(client.get('/api/workspace/').status_code,200)

    def test_login_password_is_insufficient_for_required_mfa_role(self):
        account=self.users[m.Role.REVIEWER];factor(account);client=Client()
        self.assertEqual(client.post('/login/',{'username':account.username,'password':self.password}).url,'/identity/mfa/')
        self.assertEqual(client.get('/api/workspace/').status_code,401)
        self.assertEqual(client.post('/identity/mfa/',{'code':self.otp(account)}).status_code,302)
        self.assertEqual(client.get('/api/workspace/').status_code,200)

    def test_wrong_mfa_does_not_create_full_session(self):
        account=self.users[m.Role.REVIEWER];factor(account);client=Client()
        client.post('/login/',{'username':account.username,'password':self.password})
        client.post('/identity/mfa/',{'code':'invalid'})
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_pending_login_expires_after_five_minutes(self):
        client=Client();client.post('/login/',{'username':self.users[m.Role.REVIEWER].username,'password':self.password})
        with patch('django.utils.timezone.now',return_value=self.now+timedelta(minutes=6)):
            self.assertEqual(client.get('/identity/mfa/setup/').status_code,401)

    def test_pending_login_invalidated_by_role_change(self):
        client=Client();account=self.users[m.Role.TECH]
        m.Account.objects.filter(pk=account.pk).update(must_change_password=True)
        client.post('/login/',{'username':account.username,'password':self.password})
        self.roles(self.current(m.Role.TECH),m.Role.MANAGER)
        self.assertEqual(client.get('/identity/mfa/setup/').status_code,401)

    def test_enrollment_encrypts_secret_and_emits_single_use_recovery_codes(self):
        account=self.users[m.Role.REVIEWER];client=Client()
        client.post('/login/',{'username':account.username,'password':self.password})
        response=client.get('/identity/mfa/setup/');self.assertEqual(response.status_code,200)
        secret=response.context['secret'];device=m.MFADevice.objects.get(account=account)
        self.assertNotIn(secret,device.encrypted_secret)
        code=pyotp.TOTP(secret).at(self.now)
        response=client.post('/identity/mfa/setup/',{'code':code})
        self.assertEqual(response.status_code,200);self.assertEqual(len(response.context['codes']),8)
        self.assertEqual(client.get('/api/workspace/').status_code,200)
        recovery=response.context['codes'][0]
        self.assertTrue(i.factor_check(account.pk,recovery))
        self.assertFalse(i.factor_check(account.pk,recovery))
        self.assertNotIn(recovery,json.dumps(list(m.Event.objects.values('detail'))))
        self.assertEqual(client.get('/identity/mfa/qr/').status_code,404)

    def test_totp_replay_rejected_across_sessions(self):
        account=self.users[m.Role.TECH];code=self.otp(account)
        self.assertTrue(i.factor_check(account.pk,code));self.assertFalse(i.factor_check(account.pk,code))

    def test_tampered_mfa_ciphertext_fails_closed(self):
        account=self.users[m.Role.TECH];factor(account)
        m.MFADevice.objects.filter(account=account).update(encrypted_secret='corrupted')
        with self.assertRaises(DomainError):i.factor_check(account.pk,'123456')

    def test_initial_password_cannot_access_business_routes(self):
        account=self.users[m.Role.TECH]
        m.Account.objects.filter(pk=account.pk).update(must_change_password=True)
        client=session_for(self.current(m.Role.TECH))
        self.assertEqual(client.get('/api/workspace/').status_code,403)
        self.assertEqual(client.get('/identity/password/').status_code,200)

    def test_mfa_enrollment_cannot_be_replaced_by_get(self):
        account=self.users[m.Role.TECH];client=session_for(account)
        before=m.MFADevice.objects.get(account=account).encrypted_secret
        self.assertEqual(client.get('/identity/mfa/setup/').status_code,409)
        self.assertEqual(m.MFADevice.objects.get(account=account).encrypted_secret,before)

    def test_expiration_is_idle_and_absolute(self):
        for field,seconds in [('last_activity',1801),('login_at',28801)]:
            client=session_for(self.users[m.Role.TECH]);session=client.session;session[field]=self.now.timestamp()-seconds;session.save()
            self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_normal_activity_does_not_refresh_reauth(self):
        client=session_for(self.users[m.Role.ADMIN]);before=client.session['reauth_at']
        with patch('django.utils.timezone.now',return_value=self.now+timedelta(seconds=301)):
            client.get('/')
            self.assertEqual(client.session['reauth_at'],before)
            self.assertEqual(self.api('disable',self.users[m.Role.TECH].pk,{'reason':'Prueba'},client).status_code,403)

    def test_no_mfa_claim_in_session_bypasses_required_factor(self):
        client=session_for(self.users[m.Role.REVIEWER],mfa=False)
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_password_change_revokes_all_sessions_and_keeps_history(self):
        account=self.users[m.Role.TECH];client=session_for(account);other=session_for(account)
        password='Unique-long-'+secrets.token_urlsafe(24)
        response=client.post('/identity/password/',{'password':password,'confirm':password})
        self.assertEqual(response.status_code,302,response.content)
        account.refresh_from_db();self.assertTrue(account.check_password(password));self.assertTrue(account.password.startswith('argon2$'))
        self.assertEqual(other.get('/api/workspace/').status_code,401)
        self.assertEqual(m.Version.objects.get(pk=self.version.pk).author_id,account.person_id)

    def test_password_length_common_and_breached_checks(self):
        account=self.users[m.Role.TECH]
        for password in ('short','a'*129,'12345678901234567890'):
            with self.subTest(password=password[:10]),self.assertRaises(DomainError):i.validate_new_password(account,password)
        i.validate_new_password(account,secrets.token_urlsafe(70))
        with patch('gestion.identity.breach_count',return_value=20),self.assertRaises(DomainError):
            i.validate_new_password(account,'Uniquephrasewithmorethan15chars')

    def test_password_service_failure_preserves_credentials(self):
        account=self.users[m.Role.TECH];client=session_for(account);before=account.password
        with patch('gestion.identity.breach_count',side_effect=DomainError('Sin servicio','CONTRASENA',503)):
            response=client.post('/identity/password/',{'password':'Newrandompassphrase-123','confirm':'Newrandompassphrase-123'})
        self.assertEqual(response.status_code,503);account.refresh_from_db();self.assertEqual(account.password,before)

    def test_ten_failures_pause_all_accounts_of_person(self):
        account=self.users[m.Role.TECH]
        other=m.Account.objects.create_user(username='alternate',person=account.person,password=self.password)
        for n in range(10):self.assertIsNone(i.password_check(account.username if n%2 else other.username,'wrong'))
        self.assertIsNone(i.password_check(other.username,self.password))
        with patch('django.utils.timezone.now',return_value=self.now+timedelta(minutes=16)):
            self.assertIsNotNone(i.password_check(other.username,self.password))

    def test_factor_failures_are_persisted_when_not_accepted(self):
        account=self.users[m.Role.REVIEWER];factor(account)
        for _ in range(10):self.assertFalse(i.factor_check(account.pk,'bad-code'))
        self.assertFalse(i.factor_check(account.pk,self.otp(account)))
        self.assertEqual(m.AuthThrottle.objects.get(key=i.throttle_key(account)).failures,10)

    def test_activation_consumes_token_and_requires_enrollment(self):
        data=self.create().json();client=Client();password='Activation-'+secrets.token_urlsafe(24)
        response=client.post('/identity/recover/',{'token':data['activation_code'],'password':password,'confirm':password})
        self.assertEqual(response.status_code,302,response.content)
        self.assertEqual(response.url,'/identity/mfa/setup/')
        self.assertEqual(client.get('/api/workspace/').status_code,401)
        self.assertEqual(client.post('/identity/recover/',{'token':data['activation_code'],'password':password,'confirm':password}).status_code,400)

    def test_recovery_requires_reference_and_recent_admin_mfa(self):
        response=self.api('recovery',self.users[m.Role.TECH].pk,{'reason':'Forgot','reset_mfa':True})
        self.assertEqual(response.status_code,400)
        self.assertFalse(m.CredentialTicket.objects.exists())

    def test_recovery_without_factor_is_rejected_and_ticket_preserved(self):
        account=self.users[m.Role.TECH];factor(account);token=self.recover(account).json()['activation_code'];client=Client()
        password='Recovery-'+secrets.token_urlsafe(24)
        response=client.post('/identity/recover/',{'token':token,'password':password,'confirm':password,'code':'bad'})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(m.CredentialTicket.objects.get(digest=i.digest(token)).used_at)
        response=client.post('/identity/recover/',{'token':token,'password':password,'confirm':password,'code':self.otp(account)})
        self.assertEqual(response.status_code,302,response.content)
        account.refresh_from_db();self.assertTrue(account.check_password(password))

    def test_recovery_can_reset_lost_factor_with_admin_reference(self):
        account=self.users[m.Role.TECH];factor(account);old=session_for(account)
        token=self.recover(account,True).json()['activation_code']
        self.assertEqual(old.get('/api/workspace/').status_code,401)
        password='Recovery-'+secrets.token_urlsafe(24)
        client=Client();response=client.post('/identity/recover/',{'token':token,'password':password,'confirm':password})
        self.assertEqual(response.url,'/identity/mfa/setup/')
        self.assertFalse(m.MFADevice.objects.filter(account=account,confirmed=True).exists())
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_expired_ticket_and_ticket_before_role_change_are_rejected(self):
        data=self.create().json();ticket=m.CredentialTicket.objects.get(digest=i.digest(data['activation_code']))
        ticket.expires_at=self.now-timedelta(seconds=1);ticket.save()
        password='Activation-'+secrets.token_urlsafe(24);client=Client()
        self.assertEqual(client.post('/identity/recover/',{'token':data['activation_code'],'password':password,'confirm':password}).status_code,400)
        data=self.create(username='new.second',work='NEW-002').json();account=m.Account.objects.get(pk=data['account_id'])
        self.roles(account,m.Role.MANAGER)
        self.assertEqual(client.post('/identity/recover/',{'token':data['activation_code'],'password':password,'confirm':password}).status_code,400)

    def test_new_ticket_invalidates_previous_ticket(self):
        account=self.users[m.Role.TECH]
        old=self.recover(account,True).json()['activation_code'];new=self.recover(account,True).json()['activation_code']
        self.assertIsNotNone(m.CredentialTicket.objects.get(digest=i.digest(old)).used_at)
        self.assertIsNone(m.CredentialTicket.objects.get(digest=i.digest(new)).used_at)

    def test_regenerated_recovery_codes_invalidate_older_codes(self):
        account=self.users[m.Role.TECH];client=session_for(account)
        first=client.post('/identity/recovery-codes/').context['codes'][0]
        second=client.post('/identity/recovery-codes/').context['codes'][0]
        self.assertFalse(i.factor_check(account.pk,first));self.assertTrue(i.factor_check(account.pk,second))

    def test_auditor_expiry_revokes_session(self):
        account=self.users[m.Role.AUDITOR];client=session_for(account)
        m.AuditorGrant.objects.filter(auditor=account.person).update(ends=self.now-timedelta(seconds=1))
        self.assertEqual(client.get('/api/workspace/').status_code,401)

    def test_admin_auditor_extension_preserves_previous_grant(self):
        account=self.users[m.Role.AUDITOR];grant=m.AuditorGrant.objects.get(auditor=account.person);before=grant.ends
        response=self.api('grant',account.pk,{'farm_id':str(self.farm.pk),'assignment_name':'Extensión','ends':(self.now+timedelta(days=30)).isoformat(),'reason':'Continuidad de encargo'})
        self.assertEqual(response.status_code,200,response.content);grant.refresh_from_db();self.assertEqual(grant.ends,before)
        self.assertEqual(m.AuditorGrant.objects.filter(auditor=account.person).count(),2)

    def test_offline_sync_after_deactivation_rejected_without_receipt(self):
        account=self.users[m.Role.TECH];client=session_for(account)
        self.api('disable',account.pk,{'reason':'Baja antes de sincronización'})
        data={'farm_id':str(self.farm.pk),'period_id':str(self.period.pk),'version_id':None,'base_revision':0,
          'author_person_id':str(account.person_id),'captured_at':self.now.isoformat(),'measured_at':'2026-11-11',
          'methodology':'Campo','values':[{'name':'carbono_reportado','value':'140.00','unit':'tCO2e'}]}
        response=client.post('/api/capture/action/sync/new/',data=json.dumps(data),content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,401);self.assertEqual(m.SyncReceipt.objects.count(),0)

    def test_identity_pages_render_for_each_role(self):
        for role in m.Role.values:
            client=session_for(self.users[role])
            for path in ('/identity/profile/','/identity/sessions/','/reauth/'):
                response=client.get(path);self.assertEqual(response.status_code,200,(role,path,response.content[:100]))
        self.assertEqual(self.admin.get('/identity/accounts/').status_code,200)

    def test_secret_pages_are_no_store(self):
        client=Client();account=self.users[m.Role.REVIEWER]
        client.post('/login/',{'username':account.username,'password':self.password})
        for path in ('/identity/mfa/setup/','/identity/mfa/qr/'):
            response=client.get(path);self.assertEqual(response.status_code,200)
            self.assertEqual(response['Cache-Control'],'no-store')


class IdentityConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.users,self.password,self.farm,self.period,self.measurement,self.version=fixture()

    def test_only_one_concurrent_totp_is_accepted(self):
        account=self.users[m.Role.TECH];secret=factor(account);code=pyotp.TOTP(secret).now()
        def attempt(_):
            close_old_connections()
            try:return i.factor_check(account.pk,code)
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),[False,True])

    def test_only_one_concurrent_recovery_code_is_accepted(self):
        account=self.users[m.Role.TECH];factor(account);code=i.new_recovery_codes(account)[0]
        def attempt(_):
            close_old_connections()
            try:return i.factor_check(account.pk,code)
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),[False,True])


class BreachLookupTests(TestCase):
    def response(self, body, status=200):
        from unittest.mock import MagicMock
        response=MagicMock();response.status=status;response.read.return_value=body
        response.__enter__.return_value=response
        return response

    def test_only_hash_prefix_is_sent_with_padding(self):
        import hashlib
        password='Synthetic lookup only, not a credential'
        hashed=hashlib.sha1(password.encode()).hexdigest().upper()
        with patch('gestion.identity.urlopen',return_value=self.response((hashed[5:]+':42\r\n').encode())) as fetch:
            self.assertEqual(i.breach_count(password),42)
            request=fetch.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.pwnedpasswords.com/range/'+hashed[:5])
            self.assertEqual(request.get_header('Add-padding'),'true')
            self.assertIsNone(request.data)
            self.assertEqual(fetch.call_args.kwargs['timeout'],6)

    def test_padding_with_zero_count_is_not_a_breach(self):
        import hashlib
        password='Synthetic padding lookup'
        hashed=hashlib.sha1(password.encode()).hexdigest().upper()
        with patch('gestion.identity.urlopen',return_value=self.response((hashed[5:]+':0\n').encode())):
            self.assertEqual(i.breach_count(password),0)

    def test_unavailable_service_fails_closed(self):
        with patch('gestion.identity.urlopen',side_effect=OSError('offline')):
            with self.assertRaises(DomainError) as error:i.breach_count('Synthetic password lookup')
            self.assertEqual(error.exception.status,503)

    def test_invalid_or_oversized_response_fails_closed(self):
        for body,status in [(b'',200),(b'NOT-A-HASH:2',200),(b'A'*2000001,200),(b'error',502)]:
            with patch('gestion.identity.urlopen',return_value=self.response(body,status)):
                with self.assertRaises(DomainError) as error:i.breach_count('Synthetic password lookup')
                self.assertEqual(error.exception.status,503)
