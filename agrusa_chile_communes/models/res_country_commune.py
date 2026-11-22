import csv
import logging
from pathlib import Path

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResCountryCommune(models.Model):
    _name = "res.country.commune"
    _description = "Comuna"
    _order = "state_id, name"

    name = fields.Char(string="Comuna", required=True, index=True)
    code = fields.Char(string="Código CUT", index=True)
    province = fields.Char(string="Provincia", index=True)
    state_id = fields.Many2one(
        "res.country.state",
        string="Región",
        required=True,
        index=True,
        ondelete="restrict",
    )
    country_id = fields.Many2one(
        "res.country",
        string="País",
        related="state_id.country_id",
        store=True,
        readonly=True,
        index=True,
    )
    active = fields.Boolean(default=True)

    _commune_name_state_unique = models.Constraint(
        "UNIQUE(name, state_id)",
        "Ya existe una comuna con este nombre en la región seleccionada.",
    )

    @api.constrains("state_id")
    def _check_chile_state(self):
        for rec in self:
            if rec.state_id.country_id.code != "CL":
                raise ValidationError("Este mantenedor está destinado a comunas de Chile.")

    @api.model
    def _load_agrusa_chile_communes(self):
        """Carga/actualiza las comunas y vincula contactos existentes sin alterar city."""
        country = self.env["res.country"].sudo().search([("code", "=", "CL")], limit=1)
        if not country:
            _logger.warning("AGRUSA Comunas: no se encontró el país CL; se omite la carga.")
            return True

        states = self.env["res.country.state"].sudo().search([("country_id", "=", country.id)])
        state_by_code = {state.code: state for state in states}

        csv_path = Path(__file__).resolve().parent.parent / "data" / "chile_communes.csv"
        created = updated = 0
        with csv_path.open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                state = state_by_code.get(row["state_code"])
                if not state:
                    _logger.warning("AGRUSA Comunas: región no encontrada: %s", row["state_code"])
                    continue

                vals = {
                    "name": row["name"].strip(),
                    "province": row["province"].strip(),
                    "state_id": state.id,
                    "code": row["number"].strip(),
                    "active": True,
                }
                commune = self.sudo().with_context(active_test=False).search([
                    ("state_id", "=", state.id),
                    ("name", "=ilike", vals["name"]),
                ], limit=1)
                if commune:
                    commune.write(vals)
                    updated += 1
                else:
                    self.sudo().create(vals)
                    created += 1

        self._sync_existing_chilean_partners(country)
        _logger.info("AGRUSA Comunas: creadas=%s actualizadas=%s", created, updated)
        return True

    @api.model
    def _sync_existing_chilean_partners(self, country=None):
        country = country or self.env["res.country"].sudo().search([("code", "=", "CL")], limit=1)
        if not country:
            return True

        partners = self.env["res.partner"].sudo().search([
            ("country_id", "=", country.id),
            ("state_id", "!=", False),
            ("city", "!=", False),
            ("commune_id", "=", False),
        ])
        communes = self.sudo().search([("country_id", "=", country.id)])
        index = {(c.state_id.id, c.name.strip().casefold()): c.id for c in communes}

        matched = 0
        for partner in partners:
            commune_id = index.get((partner.state_id.id, partner.city.strip().casefold()))
            if commune_id:
                partner.with_context(skip_commune_sync=True).write({"commune_id": commune_id})
                matched += 1
        _logger.info("AGRUSA Comunas: contactos existentes vinculados=%s", matched)
        return True
