from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    coordinator_partner_id = fields.Many2one('res.partner', string='Default Coordinator')

    def set_values(self):
        super().set_values()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('sm_learning_agreement.coordinator_partner_id', self.coordinator_partner_id.id or False)

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        partner_id = icp.get_param('sm_learning_agreement.coordinator_partner_id')
        res.update(coordinator_partner_id=int(partner_id) if partner_id else False)
        return res