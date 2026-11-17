from django.db import migrations

SQL=r'''
CREATE OR REPLACE FUNCTION va_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['status','submitted_at','values','methodology','measured_at','edit_revision']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['status','submitted_at','values','methodology','measured_at','edit_revision']) THEN
   RAISE EXCEPTION 'Identidad e historial de versión inmutables';
 END IF;
 IF OLD.status <> 'BORRADOR' AND (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN
   RAISE EXCEPTION 'Contenido enviado inmutable';
 END IF;
 IF NEW.status <> OLD.status AND NOT ((OLD.status='BORRADOR' AND NEW.status='ENVIADA') OR
     (OLD.status='ENVIADA' AND NEW.status IN ('APROBADA','DEVUELTA'))) THEN
   RAISE EXCEPTION 'Transición de versión inválida';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER sync_receipt_append_only BEFORE UPDATE OR DELETE ON gestion_syncreceipt
 FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE FUNCTION va_assignment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Asignación histórica no eliminable'; END IF;
 IF (to_jsonb(NEW)-ARRAY['ends','revoked_by_id','revocation_reason']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['ends','revoked_by_id','revocation_reason']) OR
    NEW.ends IS NULL OR NEW.ends < OLD.starts OR
    (OLD.ends IS NOT NULL AND NEW.ends > OLD.ends) THEN
   RAISE EXCEPTION 'Solo se permite finalizar una asignación, conservando el historial';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER farm_assignment_guard BEFORE UPDATE OR DELETE ON gestion_farmassignment
 FOR EACH ROW EXECUTE FUNCTION va_assignment_guard();
CREATE TRIGGER review_assignment_guard BEFORE UPDATE OR DELETE ON gestion_reviewassignment
 FOR EACH ROW EXECUTE FUNCTION va_assignment_guard();
CREATE TRIGGER owner_link_guard BEFORE UPDATE OR DELETE ON gestion_ownerlink
 FOR EACH ROW EXECUTE FUNCTION va_assignment_guard();
CREATE TRIGGER farm_no_delete BEFORE DELETE ON gestion_farm FOR EACH ROW EXECUTE FUNCTION va_no_change();
CREATE TRIGGER owner_no_delete BEFORE DELETE ON gestion_owner FOR EACH ROW EXECUTE FUNCTION va_no_change();
'''

class Migration(migrations.Migration):
    dependencies=[('gestion','0004_capture_sync')]
    # La reversión del esquema requiere un respaldo; no se elimina historial de sincronización.
    operations=[migrations.RunSQL(SQL)]
