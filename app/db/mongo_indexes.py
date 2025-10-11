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
    # Hire/termination dates for trend queries
    await employees.create_index([("date_hired", 1)], name="idx_emp_date_hired")
    await employees.create_index([("date_terminated", 1)], name="idx_emp_date_term")

    leaves = db["leaves"]
    # Indexes for leaves collection
    await leaves.create_index([("employee_id", 1)], name="idx_employee_id_leave")
    await leaves.create_index([("status", 1)], name="idx_status_leave")
    await leaves.create_index([("company_id", 1), ("status", 1)], name="idx_company_status_leave")
    await leaves.create_index([("company_id", 1), ("start_date", 1), ("end_date", 1)], name="idx_company_leave_dates")

    documents = db["documents"]
    # Indexes for documents collection
    await documents.create_index([("company_id", 1)], name="idx_company_id_doc")
    await documents.create_index([("employee_id", 1)], name="idx_employee_id_doc")
    await documents.create_index([("uploaded_at", -1)], name="idx_doc_uploaded_at")

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

    attendance = db["attendance"]
    await attendance.create_index([("company_id", 1), ("employee_id", 1), ("date", 1)], name="idx_att_company_emp_date")

    announcements = db["announcements"]
    await announcements.create_index([("company_id", 1), ("created_at", -1)], name="idx_ann_company_created")

    notifications = db["notifications"]
    await notifications.create_index([("user_id", 1), ("read", 1), ("created_at", -1)], name="idx_notif_user_read_created")

    # Jobs and time tracking
    jobs = db["jobs"]
    await jobs.create_index([("company_id", 1), ("name", 1)], unique=True, name="uniq_company_job_name")
    await jobs.create_index([("company_id", 1), ("active", 1)], name="idx_jobs_company_active")

    job_rates = db["job_rates"]
    await job_rates.create_index([("company_id", 1), ("job_id", 1), ("employee_id", 1)], unique=True, name="uniq_company_job_employee_rate")

    time_entries = db["time_entries"]
    await time_entries.create_index([("company_id", 1), ("employee_id", 1), ("date", 1)], name="idx_te_company_emp_date")
    await time_entries.create_index([("company_id", 1), ("job_id", 1), ("date", 1)], name="idx_te_company_job_date")
    await time_entries.create_index([("company_id", 1), ("employee_id", 1), ("is_active", 1)], name="idx_te_active_by_emp")

    # Job assignments
    job_assignments = db["job_assignments"]
    await job_assignments.create_index([("company_id", 1), ("job_id", 1), ("employee_id", 1)], unique=True, name="uniq_company_job_employee_assign")
    await job_assignments.create_index([("company_id", 1), ("employee_id", 1)], name="idx_assign_by_emp")
    await job_assignments.create_index([("company_id", 1), ("job_id", 1)], name="idx_assign_by_job")

    # Assignment activity feed
    assignment_activity = db["assignment_activity"]
    await assignment_activity.create_index([("company_id", 1), ("employee_id", 1), ("created_at", -1)], name="idx_assign_activity_emp_created")
    await assignment_activity.create_index([("company_id", 1), ("job_id", 1), ("employee_id", 1), ("created_at", -1)], name="idx_assign_activity_job_emp_created")
