"""Migration SQL shared by two independently owned local admission gates."""


def install(table, function, tables, default, key):
    # Inputs are fixed migration literals, never user/environment values.
    sql = f"""
CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE phase text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared({key});
 SELECT mode INTO phase FROM {table} WHERE id=1;
 IF coalesce(phase,'{default}') <> '{default}' AND NOT
    (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) THEN
  RAISE EXCEPTION 'Import writer fenced for controlled cutover' USING ERRCODE='42501';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END; $$;
"""
    for relation in tables:
        sql += f"CREATE TRIGGER cutover_writer BEFORE INSERT OR UPDATE OR DELETE ON {relation} FOR EACH ROW EXECUTE FUNCTION {function}();\n"
    return sql
