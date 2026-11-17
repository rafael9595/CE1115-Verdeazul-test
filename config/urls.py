from django.urls import path
from gestion import views, capture_views as cv, identity_views as iv

urlpatterns=[path('',views.dashboard,name='dashboard'),path('login/',iv.login_view,name='login'),
 path('logout/',iv.logout_view,name='logout'),path('reauth/',iv.reauthenticate,name='reauth'),
 path('verify/',views.verify_view,name='verify'),path('health/',views.health),
 path('action/<str:action>/<str:target>/',views.form_action,name='form_action'),
 path('api/action/<str:action>/<str:target>/',views.api_action),path('api/workspace/',views.api_workspace),
 path('api/reports/<uuid:measurement_id>/',views.report_view,name='report'),
 path('api/certificates/<uuid:certificate_id>/download/',views.certificate_download,name='download'),
 path('api/prices/<uuid:certificate_id>/',views.price_view),path('api/audit/',views.audit_view,name='audit')]

urlpatterns += [
 path('farms/',cv.farms,name='farms'),path('farms/new/',cv.farm_form,name='farm_new'),
 path('farms/<uuid:farm_id>/edit/',cv.farm_form,name='farm_edit'),
 path('owners/',cv.owner_list,name='owners'),path('assignments/',cv.assignment_list,name='assignments'),
 path('queues/',cv.queue_list,name='queues'),path('measurements/new/',cv.measurement_form,name='measurement_new'),
 path('measurements/<uuid:version_id>/edit/',cv.measurement_form,name='measurement_edit'),
 path('measurements/<uuid:measurement_id>/download/',cv.measurement_download,name='measurement_download'),
 path('capture/action/<str:action>/<str:target>/',cv.form_action,name='capture_action'),
 path('api/capture/action/<str:action>/<str:target>/',cv.api_action),
 path('api/capture/farms/',cv.api_catalog),path('api/capture/farms/<uuid:farm_id>/',cv.api_farm),
 path('api/capture/owners/',cv.api_owners),path('api/capture/assignments/',cv.api_assignments),
 path('api/capture/bootstrap/',cv.api_bootstrap),path('api/capture/queues/',cv.api_queues),
 path('campo/',cv.field_shell,name='field'),path('campo/sw.js',cv.service_worker),
 path('assets/<str:name>',cv.asset),
]

urlpatterns += [
 path('identity/profile/',iv.profile,name='profile'),
 path('identity/password/',iv.password_change,name='password_change'),
 path('identity/mfa/',iv.mfa_challenge,name='mfa_challenge'),
 path('identity/mfa/setup/',iv.mfa_setup,name='mfa_setup'),
 path('identity/mfa/qr/',iv.mfa_qr,name='mfa_qr'),
 path('identity/recover/',iv.recover,name='recover'),
 path('identity/recovery-codes/',iv.recovery_codes,name='recovery_codes'),
 path('identity/role/',iv.switch_role,name='switch_role'),
 path('identity/sessions/',iv.sessions,name='sessions'),
 path('identity/sessions/<uuid:session_id>/revoke/',iv.revoke_session,name='revoke_session'),
 path('identity/accounts/',iv.accounts,name='accounts'),
 path('identity/action/<str:action>/<str:target>/',iv.admin_action,name='identity_action'),
 path('api/identity/accounts/',iv.accounts),path('api/identity/sessions/',iv.sessions),
 path('api/identity/sessions/<uuid:session_id>/revoke/',iv.revoke_session),
 path('api/identity/action/<str:action>/<str:target>/',iv.admin_action),
]
