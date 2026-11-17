from django.db import migrations

SQL = r'''
CREATE FUNCTION va_no_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Evidencia de solo anexado: %', TG_TABLE_NAME; END; $$;
CREATE TRIGGER event_append_only BEFORE UPDATE OR DELETE ON gestion_event FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER review_append_only BEFORE UPDATE OR DELETE ON gestion_review FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER operation_append_only BEFORE UPDATE OR DELETE ON gestion_operation FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER version_no_delete BEFORE DELETE ON gestion_version FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER certificate_no_delete BEFORE DELETE ON gestion_certificate FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER amendment_no_delete BEFORE DELETE ON gestion_amendment FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER measurement_no_delete BEFORE DELETE ON gestion_measurement FOR EACH ROW EXECUTE FUNCTION va_no_change();

CREATE FUNCTION va_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['status','submitted_at','values','methodology','measured_at']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['status','submitted_at','values','methodology','measured_at']) THEN
   RAISE EXCEPTION 'Identidad e historial de versión inmutables';
 END IF;
 IF OLD.status <> 'BORRADOR' AND
    (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN
   RAISE EXCEPTION 'Contenido enviado inmutable';
 END IF;
 IF NEW.status <> OLD.status AND NOT (
   (OLD.status='BORRADOR' AND NEW.status='ENVIADA') OR
   (OLD.status='ENVIADA' AND NEW.status IN ('APROBADA','DEVUELTA'))) THEN
   RAISE EXCEPTION 'Transición de versión inválida';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER version_guard BEFORE UPDATE ON gestion_version FOR EACH ROW EXECUTE FUNCTION va_version_guard();

CREATE FUNCTION va_certificate_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['status','invalidated_at','invalidated_by_id','invalidation_reason']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['status','invalidated_at','invalidated_by_id','invalidation_reason']) THEN
   RAISE EXCEPTION 'Certificado firmado inmutable';
 END IF;
 IF NOT (OLD.status='VIGENTE' AND NEW.status='INVALIDADO' AND NEW.invalidated_at IS NOT NULL AND
         NEW.invalidated_by_id IS NOT NULL AND length(trim(NEW.invalidation_reason))>0) THEN
   RAISE EXCEPTION 'Solo se admite invalidación con motivo';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER certificate_guard BEFORE UPDATE ON gestion_certificate FOR EACH ROW EXECUTE FUNCTION va_certificate_guard();

CREATE FUNCTION va_amendment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['status','authorizer_id','technician_id','authorized_at','authorization_reason']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['status','authorizer_id','technician_id','authorized_at','authorization_reason']) OR
    NOT (OLD.status='SOLICITADA' AND NEW.status='AUTORIZADA' AND NEW.authorizer_id IS NOT NULL AND
         NEW.technician_id IS NOT NULL AND NEW.authorized_at IS NOT NULL AND length(trim(NEW.authorization_reason))>0) THEN
    RAISE EXCEPTION 'Solicitud histórica inmutable';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER amendment_guard BEFORE UPDATE ON gestion_amendment FOR EACH ROW EXECUTE FUNCTION va_amendment_guard();

CREATE FUNCTION va_period_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status='CERRADA' AND NEW.status <> 'CERRADA' THEN RAISE EXCEPTION 'No se reabre un período cerrado'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER period_guard BEFORE UPDATE ON gestion_period FOR EACH ROW EXECUTE FUNCTION va_period_guard();

CREATE FUNCTION va_role_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.role <> OLD.role THEN NEW.auth_version := OLD.auth_version+1; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER role_guard BEFORE UPDATE ON gestion_person FOR EACH ROW EXECUTE FUNCTION va_role_guard();
'''
REVERSE = '''
DROP FUNCTION va_no_change() CASCADE;
DROP FUNCTION va_version_guard() CASCADE;
DROP FUNCTION va_certificate_guard() CASCADE;
DROP FUNCTION va_amendment_guard() CASCADE;
DROP FUNCTION va_period_guard() CASCADE;
DROP FUNCTION va_role_guard() CASCADE;
'''

class Migration(migrations.Migration):
    dependencies=[('gestion','0001_initial')]
    operations=[migrations.RunSQL(SQL,REVERSE)]
