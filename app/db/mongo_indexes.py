from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.mongo import get_mongo_db


async def ensure_indexes(db: AsyncIOMotorDatabase | None = None) -> None:
    """Create required MongoDB indexes (idempotent)."""
    if db is None:
        db = get_mongo_db()

    users = db["users"]
    # Unique index on email
    await users.create_index([("email", 1)], unique=True, name="uniq_email")
    # Index on company_id for filtering
    await users.create_index([("company_id", 1)], name="idx_company_id")

    employees = db["employees"]
    # Index on company_id for scoping
    await employees.create_index([("company_id", 1)], name="idx_company_id_emp")
    # Optional index on email to accelerate lookups
    await employees.create_index([("email", 1)], name="idx_employee_email")

    leaves = db["leaves"]
    # Indexes for leaves collection
    await leaves.create_index([("employee_id", 1)], name="idx_employee_id_leave")
    await leaves.create_index([("status", 1)], name="idx_status_leave")
    await leaves.create_index([("company_id", 1), ("status", 1)], name="idx_company_status_leave")

    documents = db["documents"]
    # Indexes for documents collection
    await documents.create_index([("company_id", 1)], name="idx_company_id_doc")
    await documents.create_index([("employee_id", 1)], name="idx_employee_id_doc")

    lookups = db["lookups"]
    # Composite index on (category, code)
    await lookups.create_index([("category", 1), ("code", 1)], name="idx_category_code_lookup")

    settings = db["settings"]
    # Ensure one settings document per company (typical)
    await settings.create_index([("company_id", 1)], unique=True, name="uniq_company_id_settings")

    invites = db["invites"]
    # Unique token for invites
    await invites.create_index([("token", 1)], unique=True, name="uniq_invite_token")
    await invites.create_index([("expires_at", 1)], name="idx_invite_expires_at")
