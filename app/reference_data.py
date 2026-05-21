from __future__ import annotations

from app.models import EntityReference


# Common standard Dataverse/Dynamics 365 tables used by Sales, Customer Service,
# activity tracking, and security/admin troubleshooting.
STANDARD_DYNAMICS_ENTITIES = [
    EntityReference(
        label="Account",
        logical_name="account",
        area="Sales",
        description="Companies, customers, vendors, or potential customers.",
    ),
    EntityReference(
        label="Contact",
        logical_name="contact",
        area="Sales",
        description="People associated with accounts or customer interactions.",
    ),
    EntityReference(
        label="Lead",
        logical_name="lead",
        area="Sales",
        description="Prospects that may be qualified into opportunities.",
    ),
    EntityReference(
        label="Opportunity",
        logical_name="opportunity",
        area="Sales",
        description="Potential sales engagements and pipeline records.",
    ),
    EntityReference(
        label="Quote",
        logical_name="quote",
        area="Sales",
        description="Formal offers with products, pricing, and terms.",
    ),
    EntityReference(
        label="Order",
        logical_name="salesorder",
        area="Sales",
        description="Accepted sales transactions created from quotes or opportunities.",
    ),
    EntityReference(
        label="Invoice",
        logical_name="invoice",
        area="Sales",
        description="Billed sales transactions.",
    ),
    EntityReference(
        label="Product",
        logical_name="product",
        area="Sales",
        description="Catalog items used in opportunities, quotes, orders, and invoices.",
    ),
    EntityReference(
        label="Price List",
        logical_name="pricelevel",
        area="Sales",
        description="Pricing model used for sales transactions.",
    ),
    EntityReference(
        label="Competitor",
        logical_name="competitor",
        area="Sales",
        description="Competing organizations tracked during sales engagements.",
    ),
    EntityReference(
        label="Case",
        logical_name="incident",
        area="Customer Service",
        description="Customer service case or support incident.",
    ),
    EntityReference(
        label="Knowledge Article",
        logical_name="knowledgearticle",
        area="Customer Service",
        description="Published support knowledge content.",
    ),
    EntityReference(
        label="Queue",
        logical_name="queue",
        area="Customer Service",
        description="Work routing and ownership queue.",
    ),
    EntityReference(
        label="Email",
        logical_name="email",
        area="Activities",
        description="Email activity records.",
    ),
    EntityReference(
        label="Phone Call",
        logical_name="phonecall",
        area="Activities",
        description="Phone call activity records.",
    ),
    EntityReference(
        label="Task",
        logical_name="task",
        area="Activities",
        description="Task activity records.",
    ),
    EntityReference(
        label="Appointment",
        logical_name="appointment",
        area="Activities",
        description="Calendar appointment activity records.",
    ),
    EntityReference(
        label="User",
        logical_name="systemuser",
        area="Security",
        description="Licensed users and ownership/security context.",
    ),
    EntityReference(
        label="Team",
        logical_name="team",
        area="Security",
        description="Team ownership, access, and membership.",
    ),
    EntityReference(
        label="Business Unit",
        logical_name="businessunit",
        area="Security",
        description="Business-unit hierarchy used for security scope.",
    ),
]
