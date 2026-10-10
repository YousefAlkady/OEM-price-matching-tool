"""Odoo-version-specific helpers live here, so the move to Odoo 19 touches one file."""


def unique_constraint(name, columns, message):
    """An entry for _sql_constraints (Odoo 18). In Odoo 19, switch callers to models.Constraint here."""
    return (name, f'unique({columns})', message)
