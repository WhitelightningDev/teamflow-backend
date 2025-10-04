from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Sequence

from bson import ObjectId

from app.db.mongo import get_mongo_db, close_mongo_client
from app.db.mongo_indexes import ensure_indexes
from app.core.security import hash_password


async def seed_companies(db):
    now = datetime.utcnow()
    company_id = ObjectId("6562a0f0a0a0a0a0a0a0a0a0")  # stable id for idempotence
    company = {
        "_id": company_id,
        "name": "TeamFlow Inc",
        "address": "123 Example St, Sample City",
        "contact_email": "admin@teamflow.local",
        "created_at": now,
        "updated_at": now,
        "logo_url": None,
        "timezone": "UTC",
        "settings": {
            "notifications": {"email": True, "push": False}
        },
    }
    await db["companies"].update_one(
        {"_id": company_id}, {"$setOnInsert": company}, upsert=True
    )
    return company_id


async def seed_settings(db, company_id: ObjectId):
    now = datetime.utcnow()
    await db["settings"].update_one(
        {"company_id": company_id},
        {
            "$setOnInsert": {
                "company_id": company_id,
                "notification_settings": {"email": True, "push": False},
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )


async def seed_lookups(db):
    items: Sequence[tuple[str, str, str, int]] = [
        ("leave_types", "annual", "Annual Leave", 1),
        ("leave_types", "sick", "Sick Leave", 2),
        ("leave_types", "unpaid", "Unpaid Leave", 3),
        ("leave_types", "maternity", "Maternity Leave", 4),
        ("leave_types", "paternity", "Paternity Leave", 5),
        ("leave_statuses", "requested", "Requested", 1),
        ("leave_statuses", "approved", "Approved", 2),
        ("leave_statuses", "rejected", "Rejected", 3),
        ("leave_statuses", "cancelled", "Cancelled", 4),
        ("roles", "admin", "Admin", 1),
        ("roles", "manager", "Manager", 2),
        ("roles", "supervisor", "Supervisor", 3),
        ("roles", "hr", "HR", 4),
        ("roles", "employee", "Employee", 5),
        ("roles", "staff", "Staff", 6),
        ("roles", "guest", "Guest", 7),
        ("roles", "viewer", "Viewer", 8),
        ("roles", "payroll", "Payroll", 9),
        ("roles", "recruiter", "Recruiter", 10),
        ("roles", "trainer", "Trainer", 11),
        ("roles", "benefit_admin", "Benefits Admin", 12),
    ]
    for category, code, label, seq in items:
        await db["lookups"].update_one(
            {"category": category, "code": code},
            {"$setOnInsert": {"category": category, "code": code, "label": label, "sequence": seq}},
            upsert=True,
        )


async def seed_users(db, company_id: ObjectId):
    now = datetime.utcnow()
    users = [
        {
            "_id": ObjectId("6562a0f0a0a0a0a0a0a0a0a1"),
            "email": "admin@teamflow.local",
            "password_hash": hash_password("admin12345"),
            "first_name": "Admin",
            "last_name": "User",
            "role": "admin",
            "company_id": company_id,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "last_login": None,
            "profile_photo_url": None,
        },
        {
            "_id": ObjectId("6562a0f0a0a0a0a0a0a0a0a2"),
            "email": "manager@teamflow.local",
            "password_hash": hash_password("manager12345"),
            "first_name": "Mandy",
            "last_name": "Manager",
            "role": "manager",
            "company_id": company_id,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "last_login": None,
            "profile_photo_url": None,
        },
    ]
    for u in users:
        await db["users"].update_one({"email": u["email"]}, {"$setOnInsert": u}, upsert=True)
    return users


async def seed_employees(db, company_id: ObjectId, users):
    now = datetime.utcnow()
    employees = [
        {
            "_id": ObjectId("6562a0f0a0a0a0a0a0a0a0b1"),
            "company_id": company_id,
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "role": "staff",
            "status": "active",
            "date_hired": now,
            "date_terminated": None,
            "profile_photo": None,
            "metadata": {"department": "Engineering"},
            "tags": ["eng", "fulltime"],
            "created_at": now,
            "updated_at": now,
        },
        {
            "_id": ObjectId("6562a0f0a0a0a0a0a0a0a0b2"),
            "company_id": company_id,
            "first_name": "Bob",
            "last_name": "Brown",
            "email": "bob@example.com",
            "role": "staff",
            "status": "active",
            "date_hired": now,
            "date_terminated": None,
            "profile_photo": None,
            "metadata": {"department": "Operations"},
            "tags": ["ops"],
            "created_at": now,
            "updated_at": now,
        },
    ]
    for e in employees:
        await db["employees"].update_one({"_id": e["_id"]}, {"$setOnInsert": e}, upsert=True)
    return employees


async def seed_leaves(db, company_id: ObjectId, employees):
    now = datetime.utcnow()
    # pick the first employee
    emp_id = employees[0]["_id"]
    leaves = [
        {
            "_id": ObjectId("6562a0f0a0a0a0a0a0a0a0c1"),
            "company_id": company_id,
            "employee_id": emp_id,
            "leave_type": "annual",
            "start_date": now,
            "end_date": now,
            "reason": "Sample seed leave",
            "status": "requested",
            "requested_on": now,
            "decided_on": None,
            "approver_id": None,
            "comment": None,
            "created_at": now,
            "updated_at": now,
        }
    ]
    for l in leaves:
        await db["leaves"].update_one({"_id": l["_id"]}, {"$setOnInsert": l}, upsert=True)


async def seed_documents(db, company_id: ObjectId, employees, users):
    now = datetime.utcnow()
    doc = {
        "_id": ObjectId("6562a0f0a0a0a0a0a0a0a0d1"),
        "company_id": company_id,
        "employee_id": employees[0]["_id"],
        "category": "policy",
        "filename": "policy.pdf",
        "file_url": "/files/policy.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 123456,
        "uploaded_by": users[0]["_id"],
        "uploaded_at": now,
        "updated_at": now,
    }
    await db["documents"].update_one({"_id": doc["_id"]}, {"$setOnInsert": doc}, upsert=True)


async def main():
    db = get_mongo_db()
    # Ensure indexes before inserting
    await ensure_indexes(db)

    company_id = await seed_companies(db)
    await seed_settings(db, company_id)
    await seed_lookups(db)
    users = await seed_users(db, company_id)
    employees = await seed_employees(db, company_id, users)
    await seed_leaves(db, company_id, employees)
    await seed_documents(db, company_id, employees, users)

    print("MongoDB seed completed.")
    close_mongo_client()


if __name__ == "__main__":
    asyncio.run(main())
