from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class InteriorProject(models.Model):
    _name = "ifm.project"
    _description = "Interior Finishing Project"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True, translate=True)
    code = fields.Char(default=lambda self: _("New"), readonly=True, copy=False)
    partner_id = fields.Many2one("res.partner", string="Client", required=True, tracking=True)
    lead_id = fields.Many2one("crm.lead", string="Lead")
    address = fields.Char(required=True)
    unit_type = fields.Selection(
        [
            ("apartment", "Apartment"),
            ("villa", "Villa"),
            ("clinic", "Clinic"),
            ("palace", "Palace"),
            ("commercial_shop", "Commercial Shop"),
        ],
        default="apartment",
        required=True,
        tracking=True,
    )
    apartment_size = fields.Float(required=True)
    rooms_count = fields.Integer(required=True)
    finishing_type = fields.Selection(
        [("with_furniture", "With Furniture"), ("without_furniture", "Without Furniture")],
        required=True,
        default="without_furniture",
    )
    engineer_id = fields.Many2one("hr.employee", string="Engineer", tracking=True)
    supervisor_id = fields.Many2one("hr.employee", string="Supervisor", tracking=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("done", "Done"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )

    company_margin_percent = fields.Float(default=15.0)
    estimated_material_cost = fields.Monetary(default=0.0)
    estimated_labor_cost = fields.Monetary(default=0.0)
    estimated_total_cost = fields.Monetary(compute="_compute_estimated_total", store=True)
    change_order_cost_total = fields.Monetary(compute="_compute_change_totals", store=True)
    change_order_time_total = fields.Integer(compute="_compute_change_totals", store=True)

    task_ids = fields.One2many("ifm.task", "project_id")
    expense_ids = fields.One2many("ifm.expense", "project_id")
    payment_ids = fields.One2many("ifm.payment", "project_id")
    boq_line_ids = fields.One2many("ifm.boq.line", "project_id")
    procurement_request_ids = fields.One2many("ifm.procurement.request", "project_id")
    stock_item_ids = fields.One2many("ifm.stock.item", "project_id")
    custody_ids = fields.One2many("ifm.custody", "project_id")
    contract_ids = fields.One2many("ifm.contract", "project_id")
    document_ids = fields.One2many("ifm.document", "project_id")
    change_order_ids = fields.One2many("ifm.change.order", "project_id")

    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)

    progress_percent = fields.Float(compute="_compute_progress", store=True)
    remaining_duration = fields.Integer(compute="_compute_remaining_duration")
    material_cost = fields.Monetary(compute="_compute_costs", store=True)
    labor_cost = fields.Monetary(compute="_compute_costs", store=True)
    total_expenses = fields.Monetary(compute="_compute_costs", store=True)
    total_client_payments = fields.Monetary(compute="_compute_payments", store=True)
    remaining_client_payments = fields.Monetary(compute="_compute_payments", store=True)
    total_cost_with_margin = fields.Monetary(compute="_compute_profit", store=True)
    profit_amount = fields.Monetary(compute="_compute_profit", store=True)
    profit_percent = fields.Float(compute="_compute_profit", store=True)
    variance_amount = fields.Monetary(compute="_compute_variance", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("code", _("New")) == _("New"):
                vals["code"] = seq.next_by_code("ifm.project") or _("New")
        return super().create(vals_list)

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_("End date must be after start date."))

    @api.depends("estimated_material_cost", "estimated_labor_cost")
    def _compute_estimated_total(self):
        for rec in self:
            rec.estimated_total_cost = rec.estimated_material_cost + rec.estimated_labor_cost

    @api.depends("change_order_ids.cost_impact", "change_order_ids.time_impact_days")
    def _compute_change_totals(self):
        for rec in self:
            rec.change_order_cost_total = sum(rec.change_order_ids.mapped("cost_impact"))
            rec.change_order_time_total = int(sum(rec.change_order_ids.mapped("time_impact_days")))

    @api.depends("task_ids.completion_percent", "task_ids.state")
    def _compute_progress(self):
        for rec in self:
            if rec.task_ids:
                rec.progress_percent = sum(rec.task_ids.mapped("completion_percent")) / len(rec.task_ids)
            else:
                rec.progress_percent = 0

    @api.depends("end_date", "state")
    def _compute_remaining_duration(self):
        today = fields.Date.today()
        for rec in self:
            if rec.state == "done":
                rec.remaining_duration = 0
            elif rec.end_date:
                rec.remaining_duration = (rec.end_date - today).days
            else:
                rec.remaining_duration = 0

    @api.depends("expense_ids.amount", "expense_ids.expense_type", "expense_ids.state")
    def _compute_costs(self):
        for rec in self:
            approved = rec.expense_ids.filtered(lambda e: e.state == "approved")
            rec.material_cost = sum(approved.filtered(lambda e: e.expense_type == "material").mapped("amount"))
            rec.labor_cost = sum(approved.filtered(lambda e: e.expense_type == "labor").mapped("amount"))
            rec.total_expenses = rec.material_cost + rec.labor_cost

    @api.depends("payment_ids.amount", "payment_ids.state", "contract_ids.total_value")
    def _compute_payments(self):
        for rec in self:
            paid = sum(rec.payment_ids.filtered(lambda p: p.state == "paid").mapped("amount"))
            contract_total = sum(rec.contract_ids.mapped("total_value"))
            rec.total_client_payments = paid
            rec.remaining_client_payments = max(contract_total - paid, 0)

    @api.depends("total_expenses", "total_client_payments", "company_margin_percent", "change_order_cost_total")
    def _compute_profit(self):
        for rec in self:
            base_cost = rec.total_expenses + rec.change_order_cost_total
            margin_amount = base_cost * (rec.company_margin_percent / 100.0)
            rec.total_cost_with_margin = base_cost + margin_amount
            rec.profit_amount = rec.total_client_payments - base_cost
            rec.profit_percent = (rec.profit_amount / base_cost * 100.0) if base_cost else 0.0

    @api.depends("estimated_total_cost", "total_expenses")
    def _compute_variance(self):
        for rec in self:
            rec.variance_amount = rec.total_expenses - rec.estimated_total_cost

    def action_activate(self):
        self.write({"state": "active"})

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_open_dashboard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "ifm_project_dashboard",
            "name": _("Project Dashboard"),
            "params": {"project_id": self.id},
        }


class InteriorTask(models.Model):
    _name = "ifm.task"
    _description = "Interior Task"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True, translate=True)
    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade", tracking=True)
    assigned_employee_id = fields.Many2one("hr.employee", string="Assigned To", required=True)
    user_id = fields.Many2one(related="assigned_employee_id.user_id", store=True)
    deadline = fields.Date(required=True)
    completion_percent = fields.Float(default=0.0)
    state = fields.Selection(
        [("pending", "Pending"), ("in_progress", "In Progress"), ("done", "Done"), ("delayed", "Delayed")],
        default="pending",
        tracking=True,
    )

    @api.constrains("completion_percent")
    def _check_completion(self):
        for rec in self:
            if rec.completion_percent < 0 or rec.completion_percent > 100:
                raise ValidationError(_("Completion % must be between 0 and 100."))

    def action_mark_done(self):
        self.write({"state": "done", "completion_percent": 100})

    @api.model
    def _cron_mark_delayed_tasks(self):
        delayed_tasks = self.search([
            ("state", "in", ["pending", "in_progress"]),
            ("deadline", "<", fields.Date.today()),
        ])
        delayed_tasks.write({"state": "delayed"})
        for task in delayed_tasks:
            if task.user_id:
                task.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=task.user_id.id,
                    summary=_("Task Delayed"),
                    note=_("Task %(task)s is delayed.", task=task.name),
                )


class InteriorEngineerProfile(models.Model):
    _name = "ifm.engineer.profile"
    _description = "Engineer Analytics"

    employee_id = fields.Many2one("hr.employee", required=True)
    present_days = fields.Integer(default=0)
    absent_days = fields.Integer(default=0)
    assigned_task_count = fields.Integer(compute="_compute_task_metrics")
    completed_task_count = fields.Integer(compute="_compute_task_metrics")
    pending_task_count = fields.Integer(compute="_compute_task_metrics")
    workload_percent = fields.Float(compute="_compute_task_metrics")
    performance_score = fields.Float(compute="_compute_performance")

    @api.depends("employee_id")
    def _compute_task_metrics(self):
        task_model = self.env["ifm.task"]
        for rec in self:
            tasks = task_model.search([("assigned_employee_id", "=", rec.employee_id.id)])
            rec.assigned_task_count = len(tasks)
            rec.completed_task_count = len(tasks.filtered(lambda t: t.state == "done"))
            rec.pending_task_count = len(tasks.filtered(lambda t: t.state in ["pending", "in_progress", "delayed"]))
            rec.workload_percent = min(rec.assigned_task_count * 10, 100)

    @api.depends("assigned_task_count", "completed_task_count", "present_days", "absent_days")
    def _compute_performance(self):
        for rec in self:
            completion_ratio = rec.completed_task_count / rec.assigned_task_count if rec.assigned_task_count else 0
            attendance_total = rec.present_days + rec.absent_days
            attendance_ratio = rec.present_days / attendance_total if attendance_total else 1
            rec.performance_score = round((completion_ratio * 70 + attendance_ratio * 30) * 100, 2)


class InteriorExpense(models.Model):
    _name = "ifm.expense"
    _description = "Project Expense"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True)
    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    expense_type = fields.Selection([("material", "Material"), ("labor", "Labor")], required=True)
    amount = fields.Monetary(required=True)
    date = fields.Date(default=fields.Date.today)
    paid_from_custody = fields.Boolean(default=False)
    custody_id = fields.Many2one("ifm.custody")
    state = fields.Selection([( "draft", "Draft"), ("approved", "Approved"), ("cancel", "Cancelled")], default="draft")
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Expense amount must be positive."))

    def action_approve(self):
        for rec in self:
            rec.state = "approved"
            if rec.paid_from_custody:
                if not rec.custody_id:
                    raise UserError(_("Select custody record before approval."))
                rec.custody_id.action_deduct(rec.amount, rec.name)
            rec.message_post(body=_("Expense approved."))


class InteriorPayment(models.Model):
    _name = "ifm.payment"
    _description = "Client Payment"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True)
    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    amount = fields.Monetary(required=True)
    due_date = fields.Date(required=True)
    payment_date = fields.Date()
    state = fields.Selection(
        [("draft", "Draft"), ("paid", "Paid"), ("delayed", "Delayed")],
        default="draft",
        tracking=True,
    )
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Payment amount must be positive."))

    def action_mark_paid(self):
        self.write({"state": "paid", "payment_date": fields.Date.today()})

    @api.model
    def _cron_mark_delayed_payments(self):
        delayed = self.search([("state", "=", "draft"), ("due_date", "<", fields.Date.today())])
        delayed.write({"state": "delayed"})
        for line in delayed:
            line.message_post(body=_("Payment is delayed."))


class InteriorContract(models.Model):
    _name = "ifm.contract"
    _description = "Project Contract"

    name = fields.Char(required=True)
    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    total_value = fields.Monetary(required=True)
    payment_terms = fields.Text(required=True)
    deadline = fields.Date(required=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)


class InteriorBoqLine(models.Model):
    _name = "ifm.boq.line"
    _description = "BOQ Line"

    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    name = fields.Char(required=True, translate=True)
    quantity = fields.Float(required=True, default=1.0)
    unit_price = fields.Monetary(required=True)
    total_cost = fields.Monetary(compute="_compute_total", store=True)
    supplier_id = fields.Many2one("ifm.supplier")
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)

    @api.depends("quantity", "unit_price")
    def _compute_total(self):
        for rec in self:
            rec.total_cost = rec.quantity * rec.unit_price


class InteriorProcurementRequest(models.Model):
    _name = "ifm.procurement.request"
    _description = "Procurement Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(default=lambda self: _("New"), readonly=True, copy=False)
    project_id = fields.Many2one("ifm.project", required=True)
    requester_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    line_ids = fields.One2many("ifm.procurement.request.line", "request_id")
    state = fields.Selection(
        [("draft", "Draft"), ("to_approve", "To Approve"), ("approved", "Approved"), ("done", "Done"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )
    purchase_order_id = fields.Many2one("purchase.order")

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = seq.next_by_code("ifm.procurement.request") or _("New")
        records = super().create(vals_list)
        for rec in records:
            rec.message_post(body=_("Purchase request created."))
        return records

    def action_submit(self):
        self.write({"state": "to_approve"})

    def action_approve(self):
        self.write({"state": "approved"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_create_purchase_order(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Add at least one line."))
        po_lines = []
        for line in self.line_ids:
            po_lines.append((0, 0, {
                "name": line.name,
                "product_qty": line.quantity,
                "price_unit": line.unit_price,
                "date_planned": fields.Datetime.now(),
                "product_id": line.product_id.id,
                "product_uom": line.product_uom_id.id,
            }))
        vendor = self.line_ids.filtered("supplier_id")[:1].supplier_id.partner_id
        if not vendor:
            raise UserError(_("Select supplier in at least one line."))
        po = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "origin": self.name,
            "order_line": po_lines,
        })
        self.write({"purchase_order_id": po.id, "state": "done"})


class InteriorProcurementRequestLine(models.Model):
    _name = "ifm.procurement.request.line"
    _description = "Procurement Request Line"

    request_id = fields.Many2one("ifm.procurement.request", required=True, ondelete="cascade")
    project_id = fields.Many2one(related="request_id.project_id", store=True)
    name = fields.Char(required=True)
    product_id = fields.Many2one("product.product", required=True)
    product_uom_id = fields.Many2one("uom.uom", related="product_id.uom_po_id", readonly=False)
    quantity = fields.Float(required=True, default=1.0)
    unit_price = fields.Float(required=True, default=0.0)
    supplier_id = fields.Many2one("ifm.supplier")


class InteriorStockItem(models.Model):
    _name = "ifm.stock.item"
    _description = "Project Stock Item"

    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    category_id = fields.Many2one("product.category")
    quantity = fields.Float(required=True, default=0.0)
    used_quantity = fields.Float(default=0.0)
    remaining_quantity = fields.Float(compute="_compute_remaining", store=True)

    @api.depends("quantity", "used_quantity")
    def _compute_remaining(self):
        for rec in self:
            rec.remaining_quantity = rec.quantity - rec.used_quantity


class InteriorCustody(models.Model):
    _name = "ifm.custody"
    _description = "Engineer Custody"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True)
    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True)
    amount_assigned = fields.Monetary(required=True)
    amount_used = fields.Monetary(default=0.0)
    amount_remaining = fields.Monetary(compute="_compute_remaining", store=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)

    @api.depends("amount_assigned", "amount_used")
    def _compute_remaining(self):
        for rec in self:
            rec.amount_remaining = rec.amount_assigned - rec.amount_used

    def action_deduct(self, amount, reference):
        self.ensure_one()
        if amount <= 0:
            return
        if self.amount_remaining < amount:
            raise UserError(_("Insufficient custody balance."))
        self.amount_used += amount
        self.message_post(body=_("Deducted %(amount).2f for %(ref)s", amount=amount, ref=reference))


class InteriorDocument(models.Model):
    _name = "ifm.document"
    _description = "Project Document"

    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    room = fields.Selection(
        [
            ("kitchen", "Kitchen"),
            ("reception", "Reception"),
            ("bathroom", "Bathroom"),
            ("bedroom", "Bedroom"),
            ("other", "Other"),
        ],
        required=True,
    )
    attachment = fields.Binary(required=True, attachment=True)
    attachment_name = fields.Char()


class InteriorChangeOrder(models.Model):
    _name = "ifm.change.order"
    _description = "Project Change Order"

    project_id = fields.Many2one("ifm.project", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    description = fields.Text()
    cost_impact = fields.Monetary(required=True)
    time_impact_days = fields.Integer(default=0)
    date = fields.Date(default=fields.Date.today)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)


class InteriorSupplier(models.Model):
    _name = "ifm.supplier"
    _description = "Interior Supplier"

    name = fields.Char(required=True)
    partner_id = fields.Many2one("res.partner", required=True)
    phone = fields.Char(related="partner_id.phone", store=True)
    email = fields.Char(related="partner_id.email", store=True)
    rating = fields.Float(default=3.0)
    performance_notes = fields.Text()

    @api.constrains("rating")
    def _check_rating(self):
        for rec in self:
            if rec.rating < 0 or rec.rating > 5:
                raise ValidationError(_("Supplier rating should be between 0 and 5."))


class InteriorDashboardService(models.AbstractModel):
    _name = "ifm.dashboard.service"
    _description = "Dashboard Data Service"

    @api.model
    def executive_dashboard_data(self, date_from=False, date_to=False):
        dom = []
        if date_from:
            dom.append(("start_date", ">=", date_from))
        if date_to:
            dom.append(("end_date", "<=", date_to))
        projects = self.env["ifm.project"].search(dom)
        active = projects.filtered(lambda p: p.state == "active")
        done = projects.filtered(lambda p: p.state == "done")
        delayed = projects.filtered(lambda p: p.state != "done" and p.end_date and p.end_date < fields.Date.today())
        return {
            "kpis": {
                "total_projects": len(projects),
                "active_projects": len(active),
                "completed_projects": len(done),
                "delayed_projects": len(delayed),
                "total_profit": sum(projects.mapped("profit_amount")),
            },
            "project_progress": {
                "labels": projects.mapped("name"),
                "values": [round(x, 2) for x in projects.mapped("progress_percent")],
            },
            "expense_vs_payment": {
                "labels": projects.mapped("name"),
                "expenses": [round(x, 2) for x in projects.mapped("total_expenses")],
                "payments": [round(x, 2) for x in projects.mapped("total_client_payments")],
            },
            "profit_over_time": self._profit_over_time(projects),
            "multi_project_comparison": {
                "labels": projects.mapped("name"),
                "profit": [round(x, 2) for x in projects.mapped("profit_amount")],
                "cost": [round(x, 2) for x in projects.mapped("total_expenses")],
                "duration": [
                    (p.end_date - p.start_date).days if p.start_date and p.end_date else 0 for p in projects
                ],
            },
        }

    def _profit_over_time(self, projects):
        today = date.today()
        months = []
        values = []
        for idx in range(5, -1, -1):
            month_start = (today.replace(day=1) - timedelta(days=idx * 30)).replace(day=1)
            month_end = (month_start + timedelta(days=35)).replace(day=1) - timedelta(days=1)
            monthly = projects.filtered(lambda p: p.start_date and month_start <= p.start_date <= month_end)
            months.append(month_start.strftime("%Y-%m"))
            values.append(round(sum(monthly.mapped("profit_amount")), 2))
        return {"labels": months, "values": values}

    @api.model
    def project_dashboard_data(self, project_id):
        project = self.env["ifm.project"].browse(project_id)
        if not project.exists():
            return {}
        task_groups = {"done": 0, "pending": 0, "delayed": 0}
        for task in project.task_ids:
            if task.state == "done":
                task_groups["done"] += 1
            elif task.state == "delayed":
                task_groups["delayed"] += 1
            else:
                task_groups["pending"] += 1
        return {
            "kpis": {
                "completion": round(project.progress_percent, 2),
                "expenses": round(project.total_expenses, 2),
                "payments": round(project.total_client_payments, 2),
                "remaining_time": project.remaining_duration,
            },
            "estimated_vs_actual": {
                "labels": [_("Material"), _("Labor")],
                "estimated": [project.estimated_material_cost, project.estimated_labor_cost],
                "actual": [project.material_cost, project.labor_cost],
            },
            "cost_breakdown": {
                "labels": [_("Material"), _("Labor")],
                "values": [project.material_cost, project.labor_cost],
            },
            "task_status": {
                "labels": [_("Completed"), _("Pending"), _("Delayed")],
                "values": [task_groups["done"], task_groups["pending"], task_groups["delayed"]],
            },
        }

    @api.model
    def engineer_dashboard_data(self, employee_id=False):
        dom = []
        if employee_id:
            dom.append(("employee_id", "=", employee_id))
        profiles = self.env["ifm.engineer.profile"].search(dom)
        labels = [p.employee_id.name for p in profiles]
        return {
            "labels": labels,
            "assigned": [p.assigned_task_count for p in profiles],
            "completed": [p.completed_task_count for p in profiles],
            "pending": [p.pending_task_count for p in profiles],
            "attendance_present": [p.present_days for p in profiles],
            "attendance_absent": [p.absent_days for p in profiles],
            "performance": [p.performance_score for p in profiles],
        }
