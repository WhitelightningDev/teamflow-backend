from enum import Enum


class Role(str, Enum):
    admin = "admin"
    manager = "manager"
    supervisor = "supervisor"
    hr = "hr"
    employee = "employee"
    staff = "staff"
    guest = "guest"
    viewer = "viewer"
    payroll = "payroll"
    recruiter = "recruiter"
    trainer = "trainer"
    benefit_admin = "benefit_admin"

