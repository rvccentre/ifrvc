# -*- coding: utf-8 -*-

from datetime import timedelta
import json

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def default_get(self, fields_list):
        default_vals = super(SaleOrder, self).default_get(fields_list)
        if "sale_template_ids" in fields_list and not default_vals.get("sale_template_ids"):
            company_id = default_vals.get('company_id', False)
            company = self.env["res.company"].browse(company_id) if company_id else self.env.company
            default_vals['sale_template_ids'] = [(6, 0, company.sale_order_template_ids.ids)]
        return default_vals

    sale_template_ids = fields.Many2many('sale.order.template', string='Quotation Templates')
    old_sale_template = fields.Char()

    @api.onchange('sale_template_ids')
    def onchange_sale_template_ids_id(self):
        print(self, self._origin)
        if not self.sale_template_ids:
            self.require_signature = self._get_default_require_signature()
            self.require_payment = self._get_default_require_payment()
            self.old_sale_template = ''
            return

        templates = self.sale_template_ids.with_context(lang=self.partner_id.lang)

        order_lines = []
        old_order_line_ids = self.order_line.ids

        old_sale_templates = []
        if self.old_sale_template:
            old_sale_templates = self.env['sale.order.template'].browse(json.loads(self.old_sale_template)).ids

        templates = templates.filtered(lambda x: x._origin.id not in old_sale_templates)
        if not templates:
            if len(self.sale_template_ids) != len(old_sale_templates):
                self.old_sale_template = self.sale_template_ids._origin.ids
            return
        new_templates_order_lines = templates.mapped('sale_order_template_line_ids')

        for line in new_templates_order_lines:
            data = self._compute_line_data_for_template_change(line)

            if line.product_id:
                price = line.product_id.lst_price
                discount = 0

                if self.pricelist_id:
                    pricelist_price = self.pricelist_id.with_context(uom=line.product_uom_id.id).get_product_price(line.product_id, 1, False)

                    if self.pricelist_id.discount_policy == 'without_discount' and price:
                        discount = max(0, (price - pricelist_price) * 100 / price)
                    else:
                        price = pricelist_price

                data.update({
                    'price_unit': price,
                    'discount': discount,
                    'product_uom_qty': line.product_uom_qty,
                    'product_id': line.product_id.id,
                    'product_uom': line.product_uom_id.id,
                    'customer_lead': self._get_customer_lead(line.product_id.product_tmpl_id),
                })

            order_lines.append((0, 0, data))

        self.order_line = order_lines
        self.order_line.filtered(lambda x: x._origin.id not in old_order_line_ids)._compute_tax_id()

        # then, process the list of optional products from the templates
        option_lines = []
        template_option_lines = templates.mapped('sale_order_template_option_ids')
        for option in template_option_lines:
            data = self._compute_option_data_for_template_change(option)
            option_lines.append((0, 0, data))

        self.sale_order_option_ids = option_lines

        if not self.validity_date and max(templates.mapped('number_of_days')) > 0:
            self.validity_date = fields.Date.context_today(self) + timedelta(max(templates.mapped('number_of_days')))

        self.require_signature = any(temp.require_signature for temp in templates)
        self.require_payment = any(temp.require_payment for temp in templates)
        self.note = '\n'.join(note for note in templates.mapped('note') if note)
        self.old_sale_template = self.sale_template_ids._origin.ids

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for order in self:
            templates_with_mail_template = order.sale_template_ids.filtered(lambda x: x.mail_template_id)
            if templates_with_mail_template:
                for template in templates_with_mail_template:
                    template.send_mail(order.id)
        return res

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"
    _description = "Sales Order Line"

    # Take the description on the order templates if the product is present in it
    @api.onchange('product_id')
    def product_id_change(self):
        domain = super(SaleOrderLine, self).product_id_change()
        if self.product_id and self.order_id.sale_template_ids:
            template_order_lines = self.order_id.sale_template_ids.mapped('sale_order_template_line_ids')
            for line in template_order_lines:
                if line.product_id == self.product_id:
                    self.name = line.with_context(lang=self.order_id.partner_id.lang).name + self._get_sale_order_line_multiline_description_variants()
                    break
        return domain