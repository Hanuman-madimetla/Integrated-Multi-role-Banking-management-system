from .accountant import accountant_dashboard
from .cashier import cashier_dashboard
from .field_officer import field_officer_dashboard
from .manager import manager_dashboard

DASHBOARDS = {
    "cashier": cashier_dashboard,
    "field_officer": field_officer_dashboard,
    "accountant": accountant_dashboard,
    "manager": manager_dashboard,
}
