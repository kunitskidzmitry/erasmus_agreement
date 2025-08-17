from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class PortalLearningAgreement(CustomerPortal):
	def _get_agreement(self, agreement_id, access_token=None, allow_portal_owner=True):
		agreement = request.env['learning.agreement'].sudo().browse(int(agreement_id))
		if not agreement.exists():
			raise http.NotFound()
		# Token access
		if access_token and access_token == agreement.access_token:
			return agreement
		# Portal owner access
		if allow_portal_owner and request.env.user.has_group('base.group_portal'):
			if agreement.student_partner_id.id == request.env.user.partner_id.id:
				return agreement
		raise http.SessionExpiredException(_('You do not have access to this agreement.'))

	@http.route(['/my/learning-agreements'], type='http', auth='user', website=True)
	def portal_my_learning_agreements(self, **kwargs):
		partner = request.env.user.partner_id
		agreements = request.env['learning.agreement'].sudo().search([('student_partner_id', '=', partner.id)])
		values = {
			'page_name': 'learning_agreements',
			'agreements': agreements,
		}
		return request.render('sm_learning_agreement.portal_my_agreements', values)

	@http.route(['/my/learning-agreement/<int:agreement_id>'], type='http', auth='public', website=True, csrf=False)
	def portal_learning_agreement_form(self, agreement_id, **post):
		access_token = post.get('access_token') or request.params.get('access_token')
		agreement = self._get_agreement(agreement_id, access_token=access_token, allow_portal_owner=True)
		if request.httprequest.method == 'POST' and post:
			# Update only green fields
			allowed_fields = {
				'student_full_name', 'student_email', 'student_phone', 'student_street', 'student_street2', 'student_zip', 'student_city', 'student_country_id'
			}
			vals = {}
			for key in allowed_fields:
				if key in post and post.get(key) != '':
					vals[key] = post.get(key)
			# Handle country as Many2one id
			if 'student_country_id' in vals:
				try:
					vals['student_country_id'] = int(vals['student_country_id'])
				except Exception:
					vals.pop('student_country_id', None)
			agreement.sudo().write(vals)
			return request.redirect(f"/my/learning-agreement/{agreement_id}?access_token={agreement.access_token}")
		values = {
			'agreement': agreement,
			'access_token': access_token or agreement.access_token,
		}
		return request.render('sm_learning_agreement.portal_learning_agreement_form', values)

	@http.route(['/my/learning-agreement/<int:agreement_id>/message'], type='http', auth='public', website=True, csrf=False, methods=['POST'])
	def portal_learning_agreement_message(self, agreement_id, **post):
		access_token = post.get('access_token') or request.params.get('access_token')
		agreement = self._get_agreement(agreement_id, access_token=access_token, allow_portal_owner=True)
		body = (post.get('message') or '').strip()
		if body:
			agreement.sudo().message_post(body=body)
		return request.redirect(f"/my/learning-agreement/{agreement_id}?access_token={agreement.access_token}")