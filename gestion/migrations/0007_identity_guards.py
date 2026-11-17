from django.db import migrations


SQL = r'''
CREATE OR REPLACE FUNCTION va_role_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE roles jsonb;
BEGIN
 IF jsonb_typeof(NEW.additional_roles) <> 'array' THEN RAISE EXCEPTION 'Lista de roles inválida'; END IF;
 roles := NEW.additional_roles || jsonb_build_array(NEW.role);
 IF EXISTS (SELECT 1 FROM jsonb_array_elements_text(roles) r WHERE r NOT IN
   ('TECNICO','VERIFICADOR','ADMINISTRADOR','AUDITOR','PROPIETARIO','GERENTE','SUPERVISOR','SEGURIDAD')) THEN
   RAISE EXCEPTION 'Rol desconocido';
 END IF;
 IF roles ? 'TECNICO' AND roles ? 'VERIFICADOR' THEN RAISE EXCEPTION 'R-SoD-01: roles incompatibles por persona'; END IF;
 IF TG_OP='UPDATE' THEN
   IF NEW.work_id IS DISTINCT FROM OLD.work_id THEN RAISE EXCEPTION 'Identidad laboral histórica inmutable'; END IF;
   IF NEW.role IS DISTINCT FROM OLD.role OR NEW.additional_roles IS DISTINCT FROM OLD.additional_roles THEN
     NEW.auth_version := OLD.auth_version+1;
   ELSIF NEW.auth_version < OLD.auth_version THEN RAISE EXCEPTION 'Versión de identidad no decreciente'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER role_insert_guard BEFORE INSERT ON gestion_person FOR EACH ROW EXECUTE FUNCTION va_role_guard();
CREATE UNIQUE INDEX person_work_id_casefold ON gestion_person (upper(work_id));
CREATE UNIQUE INDEX account_username_casefold ON gestion_account (lower(username));
CREATE FUNCTION va_account_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.person_id IS DISTINCT FROM OLD.person_id THEN RAISE EXCEPTION 'La cuenta no cambia de persona histórica'; END IF;
 IF NEW.password IS DISTINCT FROM OLD.password OR NEW.is_active IS DISTINCT FROM OLD.is_active OR
    NEW.must_change_password IS DISTINCT FROM OLD.must_change_password THEN
   NEW.credential_version := OLD.credential_version+1;
 ELSIF NEW.credential_version < OLD.credential_version THEN RAISE EXCEPTION 'Versión de credencial no decreciente'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER account_identity_guard BEFORE UPDATE ON gestion_account FOR EACH ROW EXECUTE FUNCTION va_account_guard();
CREATE TRIGGER account_no_delete BEFORE DELETE ON gestion_account FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER person_no_delete BEFORE DELETE ON gestion_person FOR EACH ROW EXECUTE FUNCTION va_no_change();
'''


def upgrade_credentials(apps, schema_editor):
    # La contraseña previa se conserva como credencial inicial. Nunca se alteran certificados.
    apps.get_model('gestion','Account').objects.update(must_change_password=True)
    apps.get_model('sessions','Session').objects.all().delete()


class Migration(migrations.Migration):
    dependencies=[('gestion','0006_identity'),('sessions','0001_initial')]
    operations=[migrations.RunSQL(SQL),migrations.RunPython(upgrade_credentials)]
