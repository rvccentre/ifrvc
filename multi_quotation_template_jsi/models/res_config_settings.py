# -*- coding: utf-8 -*-

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    company_sale_order_template_ids = fields.Many2many(
        related="company_id.sale_order_template_ids", string="Default Templates", readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    def set_values(self):
        if not self.group_sale_order_template:
            self.company_sale_order_template_ids = None
            self.env['res.company'].sudo().search([]).write({
                'company_sale_order_template_ids': False,
            })
        return super(ResConfigSettings, self).set_values()
