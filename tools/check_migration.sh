#!/bin/sh
# Checks the 18.0.1.2.0 pre-migration (duplicate-part merge) on the dev database.
# Seeds an "old" database state with a duplicated article whose product link sits on the duplicate,
# runs the module upgrade, and verifies the merge kept one part, both product links, the vehicle link,
# and the unique constraint. Cleans up afterwards. Run before every release that touches migrations.
#
# Usage: tools/check_migration.sh   (expects the dev setup in C:/Odoo/devenv, see CLAUDE.md)
set -u
DEV=/c/Odoo/devenv
PG_BIN="C:/Program Files/Odoo 18.0.20251020/PostgreSQL/bin"
DB=oem_test
ODOO() { (cd "$DEV" && PYTHONPATH=C:/Odoo/run ./venv/Scripts/python.exe -m odoo -c odoo.conf -d "$DB" "$@"); }
ODOO_SHELL() { (cd "$DEV" && PYTHONPATH=C:/Odoo/run ./venv/Scripts/python.exe -m odoo shell -c odoo.conf -d "$DB" --log-level=error); }
PSQL() { PGPASSWORD=$(cat "$DEV/pg_pass.txt") "$PG_BIN/psql.exe" -h 127.0.0.1 -p 5433 -U oemdev -d "$DB" -Atc "$1"; }

TMPL=$(ODOO_SHELL <<'PY' 2>&1 | grep -o "TMPL [0-9]*" | cut -d' ' -f2
env.cr.execute("ALTER TABLE tecdoc_part DROP CONSTRAINT IF EXISTS tecdoc_part_article_id_unique")
tmpl = env['product.template'].create({'name': 'Migration check product'})
vehicle = env['tecdoc.vehicle'].create({'vehicle_id': 'MIG-CHECK', 'brand': 'TOYOTA'})
env.cr.execute("INSERT INTO tecdoc_part (name, part_number, article_id, active) VALUES ('keep','MIG','mig-999',true)")
env.cr.execute("INSERT INTO tecdoc_part (name, part_number, article_id, active, product_tmpl_id) "
               "VALUES ('dup','MIG','mig-999',true,%s) RETURNING id", (tmpl.id,))
dup_id = env.cr.fetchone()[0]
env.cr.execute("UPDATE product_template SET tecdoc_part_id=%s WHERE id=%s", (dup_id, tmpl.id))
env.cr.execute("INSERT INTO tecdoc_part_tecdoc_vehicle_rel VALUES (%s, %s)", (dup_id, vehicle.id))
env.cr.execute("INSERT INTO tecdoc_part (name, part_number, article_id, active) VALUES ('empty1','MIG-E','',true), ('empty2','MIG-E','',true)")
env.cr.execute("UPDATE ir_module_module SET latest_version='18.0.1.1.0' WHERE name='rapidapi_bdeel'")
env.cr.commit()
print("TMPL", tmpl.id)
PY
)
[ -n "$TMPL" ] || { echo "FAIL: could not seed test data"; exit 1; }

ODOO -u rapidapi_bdeel --stop-after-init --log-level=warn >/dev/null 2>&1

fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (got '$2', want '$3')"; fail=1; fi; }
check "one part left per article"      "$(PSQL "SELECT count(*) FROM tecdoc_part WHERE article_id='mig-999'")" "1"
check "kept part points to product"    "$(PSQL "SELECT product_tmpl_id = $TMPL FROM tecdoc_part WHERE article_id='mig-999'")" "t"
check "product points to kept part"    "$(PSQL "SELECT pt.tecdoc_part_id = p.id FROM product_template pt, tecdoc_part p WHERE pt.id=$TMPL AND p.article_id='mig-999'")" "t"
check "vehicle link moved to kept part" "$(PSQL "SELECT count(*) FROM tecdoc_part_tecdoc_vehicle_rel r JOIN tecdoc_part p ON p.id=r.tecdoc_part_id WHERE p.article_id='mig-999'")" "1"
check "empty article ids became NULL"  "$(PSQL "SELECT count(*) FROM tecdoc_part WHERE part_number='MIG-E' AND article_id IS NULL")" "2"
check "unique constraint present"      "$(PSQL "SELECT count(*) FROM pg_constraint WHERE conname='tecdoc_part_article_id_unique'")" "1"

PSQL "UPDATE product_template SET tecdoc_part_id=NULL WHERE id=$TMPL" >/dev/null
PSQL "DELETE FROM tecdoc_part WHERE part_number IN ('MIG','MIG-E')" >/dev/null
PSQL "DELETE FROM tecdoc_vehicle WHERE vehicle_id='MIG-CHECK'" >/dev/null
PSQL "DELETE FROM product_product WHERE product_tmpl_id=$TMPL" >/dev/null
PSQL "DELETE FROM product_template WHERE id=$TMPL" >/dev/null
[ $fail = 0 ] && echo "migration check passed" || echo "migration check FAILED"
exit $fail
