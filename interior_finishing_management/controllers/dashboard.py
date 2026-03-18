from odoo import http
from odoo.http import request


class IFMDashboardController(http.Controller):

    @http.route('/ifm/dashboard/executive', type='json', auth='user')
    def executive_dashboard(self, date_from=None, date_to=None):
        return request.env['ifm.dashboard.service'].sudo().executive_dashboard_data(date_from, date_to)

    @http.route('/ifm/dashboard/project', type='json', auth='user')
    def project_dashboard(self, project_id):
        return request.env['ifm.dashboard.service'].sudo().project_dashboard_data(int(project_id))

    @http.route('/ifm/dashboard/engineer', type='json', auth='user')
    def engineer_dashboard(self, employee_id=None):
        employee = int(employee_id) if employee_id else False
        return request.env['ifm.dashboard.service'].sudo().engineer_dashboard_data(employee)
