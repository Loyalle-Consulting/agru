from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_chilean_address = fields.Boolean(
        compute="_compute_is_chilean_address",
        string="Es dirección chilena",
    )

    commune_id = fields.Many2one(
        "res.country.commune",
        string="Comuna",
        index=True,
        ondelete="restrict",
        help="Comuna asociada a la región seleccionada. Al elegirla se mantiene sincronizado el campo estándar Ciudad.",
    )

    @api.depends("country_id")
    def _compute_is_chilean_address(self):
        for partner in self:
            partner.is_chilean_address = partner.country_id.code == "CL"

    @api.onchange("commune_id")
    def _onchange_commune_id_agrusa(self):
        if self.commune_id:
            self.city = self.commune_id.name
            if self.state_id != self.commune_id.state_id:
                self.state_id = self.commune_id.state_id
            if self.country_id != self.commune_id.country_id:
                self.country_id = self.commune_id.country_id

    @api.onchange("state_id")
    def _onchange_state_id_agrusa_commune(self):
        if self.commune_id and self.commune_id.state_id != self.state_id:
            self.commune_id = False
            self.city = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            commune_id = vals.get("commune_id")
            if commune_id and not self.env.context.get("skip_commune_sync"):
                commune = self.env["res.country.commune"].browse(commune_id)
                vals["city"] = commune.name
                vals["state_id"] = commune.state_id.id
                vals["country_id"] = commune.country_id.id
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if not self.env.context.get("skip_commune_sync") and vals.get("commune_id"):
            commune = self.env["res.country.commune"].browse(vals["commune_id"])
            vals["city"] = commune.name
            vals["state_id"] = commune.state_id.id
            vals["country_id"] = commune.country_id.id
        elif not self.env.context.get("skip_commune_sync") and vals.get("state_id"):
            new_state_id = vals["state_id"]
            if any(p.commune_id and p.commune_id.state_id.id != new_state_id for p in self):
                vals["commune_id"] = False
        return super().write(vals)
