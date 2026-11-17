import os
from datetime import timedelta
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from django.utils import timezone
from gestion import models as m
from certificados.demo import sample_payload


class Command(BaseCommand):
    help='Crea datos sintéticos de prueba en una base vacía; no modifica usuarios existentes.'
    def handle(self,*args,**options):
        if os.environ.get('ALLOW_DEMO')!='1': raise CommandError('Esta operación exige ALLOW_DEMO=1.')
        password=os.environ.get('DEMO_PASSWORD','')
        if len(password)<15: raise CommandError('Configure DEMO_PASSWORD con 15 o más caracteres.')
        if m.Measurement.objects.exists():
            self.stdout.write('Ya hay datos. Se conserva el estado existente.'); return
        if m.Account.objects.exists(): raise CommandError('La base tiene cuentas; no se realiza una carga parcial.')
        with transaction.atomic():
            people={}
            for username,role in [('tecnico',m.Role.TECH),('verificador',m.Role.REVIEWER),('administrador',m.Role.ADMIN),
                ('auditor',m.Role.AUDITOR),('propietario',m.Role.OWNER),('gerente',m.Role.MANAGER),
                ('supervisor',m.Role.SUPERVISOR),('seguridad',m.Role.SECURITY),('propietario_ajeno',m.Role.OWNER),
                ('verificador_2',m.Role.REVIEWER)]:
                person=m.Person.objects.create(work_id='DEMO-'+username.upper(),role=role)
                m.Account.objects.create_user(username=username,password=password,person=person,must_change_password=True)
                people[username]=person
            owner=m.Owner.objects.create(name='Propietario de prueba',contact='contacto-demo@example.invalid')
            foreign=m.Owner.objects.create(name='Propietario ajeno',contact='ajeno@example.invalid')
            m.OwnerLink.objects.create(person=people['propietario'],owner=owner)
            m.OwnerLink.objects.create(person=people['propietario_ajeno'],owner=foreign)
            period=m.Period.objects.create(name='Período de demostración')
            sample=sample_payload()
            for i,label in enumerate(['A · Emisión y reemplazo','B · Devolución','C · Concurrencia'],1):
                farm=m.Farm.objects.create(registry_number=f'DEMO-{i:03}',name=label,owner=owner,
                    area_ha='10.50',polygon=sample['farm']['polygon_wgs84'])
                m.FarmAssignment.objects.create(farm=farm,technician=people['tecnico'])
                measurement=m.Measurement.objects.create(farm=farm,period=period,technician=people['tecnico'])
                m.ReviewAssignment.objects.create(measurement=measurement,reviewer=people['verificador'])
                m.ReviewAssignment.objects.create(measurement=measurement,reviewer=people['verificador_2'])
                m.Version.objects.create(measurement=measurement,number=1,author=people['tecnico'],status='ENVIADA',
                    measured_at=timezone.localdate(),methodology='Demostración sintética; no acredita carbono real',
                    values=sample['measurement']['values'],submitted_at=timezone.now())
                m.AuditorGrant.objects.create(auditor=people['auditor'],farm=farm,assignment_name='Encargo de prueba',
                    ends=timezone.now()+timedelta(days=30))
        self.stdout.write('Datos de prueba creados. Usuarios: '+', '.join(people))
        self.stdout.write('Contraseña: use la generada localmente; no se imprime en registros.')
