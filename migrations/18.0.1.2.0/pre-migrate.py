import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Merge duplicate parts (same TecDoc article) before the unique(article_id) constraint is added."""
    if not version:
        return
    cr.execute("UPDATE tecdoc_part SET article_id = NULL WHERE article_id = ''")
    cr.execute("""
        CREATE TEMP TABLE tecdoc_part_dup ON COMMIT DROP AS
        SELECT id, keep_id FROM (
            SELECT id, min(id) OVER (PARTITION BY article_id) AS keep_id
            FROM tecdoc_part WHERE article_id IS NOT NULL
        ) ranked WHERE id <> keep_id
    """)
    cr.execute("SELECT count(*) FROM tecdoc_part_dup")
    duplicates = cr.fetchone()[0]
    if not duplicates:
        return
    cr.execute("UPDATE product_template pt SET tecdoc_part_id = d.keep_id FROM tecdoc_part_dup d WHERE pt.tecdoc_part_id = d.id")
    cr.execute("UPDATE tecdoc_part_image i SET part_id = d.keep_id FROM tecdoc_part_dup d WHERE i.part_id = d.id")
    cr.execute("UPDATE tecdoc_part_cross_reference x SET part_id = d.keep_id FROM tecdoc_part_dup d WHERE x.part_id = d.id")
    cr.execute("""
        INSERT INTO tecdoc_part_tecdoc_vehicle_rel (tecdoc_part_id, tecdoc_vehicle_id)
        SELECT DISTINCT d.keep_id, r.tecdoc_vehicle_id
        FROM tecdoc_part_tecdoc_vehicle_rel r JOIN tecdoc_part_dup d ON r.tecdoc_part_id = d.id
        ON CONFLICT DO NOTHING
    """)
    cr.execute("DELETE FROM tecdoc_part WHERE id IN (SELECT id FROM tecdoc_part_dup)")
    _logger.info("Merged %s duplicate TecDoc parts before adding the unique article constraint", duplicates)
