from odoo import api, fields, models, _, exceptions
from odoo.exceptions import AccessError, UserError
from datetime import timedelta
import base64
import secrets


class LearningAgreement(models.Model):
    _name = 'learning.agreement'
    _description = 'Learning Agreement'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Agreement Reference', default=lambda self: _('New'), copy=False, tracking=True)

    # Parties
    student_partner_id = fields.Many2one('res.partner', string='Student', required=True, tracking=True)
    coordinator_partner_id = fields.Many2one('res.partner', string='Coordinator', tracking=True,
                                             help='International coordinator responsible for this agreement')

    # Student (green) fields
    student_full_name = fields.Char(string='Student Full Name', tracking=True)
    student_email = fields.Char(string='Student Email', tracking=True)
    student_phone = fields.Char(string='Student Phone', tracking=True)
    student_street = fields.Char(string='Street', tracking=True)
    student_street2 = fields.Char(string='Street 2', tracking=True)
    student_zip = fields.Char(string='ZIP', tracking=True)
    student_city = fields.Char(string='City', tracking=True)
    student_country_id = fields.Many2one('res.country', string='Country', tracking=True)

    # Admin (yellow) fields
    mobility_start_date = fields.Date(string='Mobility Start Date', tracking=True)
    mobility_end_date = fields.Date(string='Mobility End Date', tracking=True)
    learning_outcomes = fields.Text(string='Learning Outcomes', tracking=True)

    host_org_name = fields.Char(string='Host Organization', tracking=True)
    host_org_street = fields.Char(string='Host Org Street', tracking=True)
    host_org_street2 = fields.Char(string='Host Org Street 2', tracking=True)
    host_org_zip = fields.Char(string='Host Org ZIP', tracking=True)
    host_org_city = fields.Char(string='Host Org City', tracking=True)
    host_org_country_id = fields.Many2one('res.country', string='Host Org Country', tracking=True)

    host_responsible_name = fields.Char(string='Host Responsible Name', tracking=True)
    host_responsible_email = fields.Char(string='Host Responsible Email', tracking=True)
    host_responsible_phone = fields.Char(string='Host Responsible Phone', tracking=True)

    # Workflow
    state = fields.Selection([
        ('draft', 'Draft'),
        ('student_input', 'Student Input Pending'),
        ('ready', 'Ready for Signature'),
        ('sent', 'Signature Requested'),
        ('signed', 'Signed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    # Portal security
    access_token = fields.Char('Access Token', copy=False, index=True)

    # Generated document and signature
    contract_attachment_id = fields.Many2one('ir.attachment', string='Contract PDF', copy=False)
    sign_request_id = fields.Many2one('sign.request', string='Sign Request', copy=False)
    signature_sent_date = fields.Datetime(string='Signature Sent On', copy=False)
    signature_deadline = fields.Date(string='Signature Deadline', copy=False)

    signature_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('waiting', 'Waiting for Signatures'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Signature Status', compute='_compute_signature_status')

    # Computed helpers
    access_url = fields.Char('Portal URL', compute='_compute_access_url', readonly=True)

    _sql_constraints = [
        ('access_token_unique', 'unique(access_token)', 'Access Token must be unique.'),
    ]

    @api.depends('sign_request_id.state')
    def _compute_signature_status(self):
        for record in self:
            if not record.sign_request_id:
                record.signature_status = 'not_sent'
            else:
                state = record.sign_request_id.state
                if state in ('cancel', 'canceled'):
                    record.signature_status = 'cancelled'
                elif state in ('signed', 'completed', 'done'):
                    record.signature_status = 'completed'
                else:
                    record.signature_status = 'waiting'

    @api.depends('access_token', 'id')
    def _compute_access_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for record in self:
            if record.access_token:
                record.access_url = f"{base}/my/learning-agreement/{record.id}?access_token={record.access_token}"
            else:
                record.access_url = False

    @api.model
    def create(self, vals):
        if not vals.get('access_token'):
            vals['access_token'] = secrets.token_urlsafe(24)
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('learning.agreement') or _('New')
        record = super().create(vals)
        record._ensure_coordinator_partner()
        record.message_subscribe(partner_ids=[pid for pid in [record.student_partner_id.id, record.coordinator_partner_id.id] if pid])
        return record

    def write(self, vals):
        self._check_portal_write_permissions(vals)
        result = super().write(vals)
        return result

    # Permissions: allow portal users (students) to edit only green fields on their agreement
    def _check_portal_write_permissions(self, incoming_vals):
        if self.env.user.has_group('sm_learning_agreement.group_learning_agreement_manager'):
            return
        if self.env.user.has_group('base.group_portal'):
            allowed_fields = {
                'student_full_name',
                'student_email',
                'student_phone',
                'student_street',
                'student_street2',
                'student_zip',
                'student_city',
                'student_country_id',
            }
            extra = set(incoming_vals.keys()) - allowed_fields
            if extra:
                raise AccessError(_('You are only allowed to edit your own contact fields.'))
            # Ensure user is owner of the record
            for rec in self:
                if rec.student_partner_id != self.env.user.partner_id:
                    raise AccessError(_('You can only modify your own agreement.'))
        else:
            # Other users cannot write
            if not self.env.user._is_admin():
                raise AccessError(_('You do not have permission to modify this agreement.'))

    def _ensure_coordinator_partner(self):
        for rec in self:
            if rec.coordinator_partner_id:
                continue
            # Pull from settings if available
            coordinator_pid = self.env['ir.config_parameter'].sudo().get_param('sm_learning_agreement.coordinator_partner_id')
            if coordinator_pid:
                rec.coordinator_partner_id = int(coordinator_pid)
            else:
                rec.coordinator_partner_id = self.env.user.partner_id.id

    # Actions
    def action_send_student_form_email(self):
        template = self.env.ref('sm_learning_agreement.mail_student_form_invite', raise_if_not_found=False)
        for rec in self:
            if not rec.student_partner_id.email:
                raise UserError(_('Student partner must have an email address.'))
            if not rec.access_token:
                rec.access_token = secrets.token_urlsafe(24)
            if template:
                template.send_mail(rec.id, force_send=True)
            else:
                rec.message_post(body=_('Invite email template not found. Please configure mail template.'), message_type='notification')

    def _render_contract_pdf(self):
        self.ensure_one()
        report = self.env.ref('sm_learning_agreement.action_report_learning_agreement')
        if not report:
            raise UserError(_('Learning Agreement report is not defined.'))
        pdf_content, content_type = report._render_qweb_pdf([self.id])
        # Create or replace attachment
        attachment_vals = {
            'name': f"{self.name}_Learning_Agreement.pdf",
            'type': 'binary',
            'datas': base64.b64encode(pdf_content).decode(),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        }
        if self.contract_attachment_id:
            self.contract_attachment_id.write(attachment_vals)
        else:
            self.contract_attachment_id = self.env['ir.attachment'].create(attachment_vals)
        return self.contract_attachment_id

    def action_generate_pdf(self):
        for rec in self:
            rec._render_contract_pdf()
        return True

    def action_send_for_signature(self):
        SignTemplate = self.env['sign.template']
        SignItemRole = self.env['sign.item.role']
        SignRequest = self.env['sign.request']

        for rec in self:
            # Ensure required parties
            if not rec.student_partner_id or not rec.coordinator_partner_id:
                raise UserError(_('Both student and coordinator must be set.'))
            # Render document
            attachment = rec._render_contract_pdf()

            # Create or reuse roles
            student_role = SignItemRole.search([('name', '=', 'Student')], limit=1)
            if not student_role:
                student_role = SignItemRole.create({'name': 'Student', 'sequence': 10})
            coordinator_role = SignItemRole.search([('name', '=', 'Coordinator')], limit=1)
            if not coordinator_role:
                coordinator_role = SignItemRole.create({'name': 'Coordinator', 'sequence': 20})

            # Create a one-off template from the generated PDF with two signature boxes
            template = SignTemplate.create({
                'name': f"Learning Agreement {rec.name}",
                'attachment_id': attachment.id,
                'responsible_id': self.env.user.id,
                'sign_item_ids': [
                    (0, 0, {
                        'name': 'Student Signature',
                        'type_id': self.env.ref('sign.sign_item_type_signature').id,
                        'role_id': student_role.id,
                        'page': 1,
                        'posX': 0.10,
                        'posY': 0.10,
                        'width': 0.30,
                        'height': 0.07,
                    }),
                    (0, 0, {
                        'name': 'Coordinator Signature',
                        'type_id': self.env.ref('sign.sign_item_type_signature').id,
                        'role_id': coordinator_role.id,
                        'page': 1,
                        'posX': 0.60,
                        'posY': 0.10,
                        'width': 0.30,
                        'height': 0.07,
                    }),
                ]
            })

            # Create sign request with the two roles mapped to partners
            request = SignRequest.create({
                'reference': f"LA-{rec.name}",
                'template_id': template.id,
                'request_item_ids': [
                    (0, 0, {
                        'partner_id': rec.student_partner_id.id,
                        'role_id': student_role.id,
                        'mail_sent_order': 1,
                    }),
                    (0, 0, {
                        'partner_id': rec.coordinator_partner_id.id,
                        'role_id': coordinator_role.id,
                        'mail_sent_order': 2,
                    }),
                ]
            })

            # Send emails to signers
            request.action_send_mail()

            rec.write({
                'sign_request_id': request.id,
                'state': 'sent',
                'signature_sent_date': fields.Datetime.now(),
            })
        return True

    def action_send_signature_reminder(self):
        for rec in self:
            if not rec.sign_request_id:
                raise UserError(_('No signature request to remind.'))
            rec.sign_request_id.action_send_mail()
            rec.message_post(body=_('Signature reminder sent.'), message_type='notification')
        return True

    @api.model
    def cron_send_overdue_signature_reminders(self):
        # Find agreements sent more than 7 days ago and not signed yet
        seven_days_ago = fields.Datetime.now() - timedelta(days=7)
        overdue = self.search([
            ('state', '=', 'sent'),
            ('signature_sent_date', '<=', seven_days_ago),
        ])
        for rec in overdue:
            try:
                rec.action_send_signature_reminder()
            except Exception as e:
                rec.message_post(body=_('Failed to send reminder: %s') % e)
        return True

    @api.model
    def cron_sync_signature_state(self):
        agreements = self.search([('sign_request_id', '!=', False)])
        for rec in agreements:
            if not rec.sign_request_id:
                continue
            state = rec.sign_request_id.state
            if state in ('signed', 'completed', 'done') and rec.state != 'signed':
                rec.state = 'signed'
            elif state in ('cancel', 'canceled') and rec.state != 'cancelled':
                rec.state = 'cancelled'
        return True

    def action_mark_ready(self):
        for rec in self:
            rec.state = 'ready'

    def action_set_student_pending(self):
        for rec in self:
            rec.state = 'student_input'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    # Portal helpers
    def action_invite_student_to_portal(self):
        """Invite the student partner to portal access and send a signup email."""
        portal_group = self.env.ref('base.group_portal')
        template = self.env.ref('portal.mail_template_data_portal_welcome', raise_if_not_found=False)
        for rec in self:
            partner = rec.student_partner_id
            if not partner.email:
                raise UserError(_('Student partner must have an email address.'))
            if partner.user_ids:
                # Ensure the main user is in portal group
                partner.user_ids[0].write({'groups_id': [(4, portal_group.id, 0)]})
            else:
                # Create user in portal
                user = self.env['res.users'].with_context(no_reset_password=True).create({
                    'name': partner.name or rec.student_full_name or 'Student',
                    'login': partner.email,
                    'email': partner.email,
                    'partner_id': partner.id,
                    'groups_id': [(6, 0, [portal_group.id])],
                })
                # Send welcome template with signup URL
                if template:
                    template.with_context(lang=user.lang).send_mail(partner.id, force_send=True)
            rec.message_post(body=_('Portal invitation sent to %s') % partner.email, message_type='notification')