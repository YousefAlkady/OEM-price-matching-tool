import json
import logging
from datetime import timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class TecdocApiCache(models.Model):
    _name = 'tecdoc.api.cache'
    _description = 'TecDoc API Response Cache'

    key = fields.Char(required=True, index=True)
    endpoint = fields.Char()
    response = fields.Text()
    expires_at = fields.Datetime(index=True)
    hit_count = fields.Integer(default=0)

    _sql_constraints = [('key_unique', 'unique(key)', 'Cache key must be unique.')]

    @api.model
    def get_valid(self, key):
        entry = self.search([('key', '=', key), ('expires_at', '>', fields.Datetime.now())], limit=1)
        if not entry:
            return None
        entry.hit_count += 1
        return json.loads(entry.response)

    @api.model
    def store(self, key, endpoint, data, ttl_days):
        vals = {
            'endpoint': endpoint,
            'response': json.dumps(data),
            'expires_at': fields.Datetime.now() + timedelta(days=ttl_days),
        }
        entry = self.search([('key', '=', key)], limit=1)
        if entry:
            entry.write(vals)
            return
        try:
            # a parallel request may have stored the same key first
            with self.env.cr.savepoint():
                self.create(dict(vals, key=key))
        except Exception as exc:
            _logger.debug("Cache store skipped for %s: %s", key, exc)

    @api.autovacuum
    def _gc_expired(self):
        self.search([('expires_at', '<', fields.Datetime.now())]).unlink()
