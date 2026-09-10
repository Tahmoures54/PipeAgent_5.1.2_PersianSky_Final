#!/usr/bin/env python
# -*- coding: utf-8 -*-
# reset_admin.py - Reset admin password or list users

import sys
import os
from getpass import getpass

# Add project root to path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.manager import DatabaseManager
from security.hashing import hash_password
from db.models import User


def list_users(db):
    """Show all existing usernames"""
    with db.session_scope() as session:
        users = session.query(User).all()
        if not users:
            print("No users found in database.")
            return
        print("\nExisting users:")
        for u in users:
            print(f"  - {u.username} (active: {u.is_active})")


def reset_password(db, username, new_password):
    """Update password for given username"""
    with db.session_scope() as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            print(f"User '{username}' not found.")
            return False
        user.password_hash = hash_password(new_password)
        session.commit()
        print(f"Password for user '{username}' has been reset.")
        return True


def create_admin(db, username, password):
    """Create a new admin user"""
    with db.session_scope() as session:
        existing = session.query(User).filter(User.username == username).first()
        if existing:
            print(f"User '{username}' already exists. Use reset instead.")
            return False
        admin = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_active=True
        )
        session.add(admin)
        session.commit()
        print(f"Admin user '{username}' created successfully.")
        return True


def main():
    db = DatabaseManager()
    if not db.initialize():
        print("Failed to initialize database.")
        return

    print("\n=== Admin Password Reset / User Management ===\n")
    print("1. List all users")
    print("2. Reset password for existing user")
    print("3. Create new admin user")
    choice = input("Select option (1/2/3): ").strip()

    if choice == "1":
        list_users(db)
    elif choice == "2":
        username = input("Enter username: ").strip()
        if not username:
            print("Username cannot be empty.")
            return
        new_pass = getpass("Enter new password: ")
        confirm = getpass("Confirm password: ")
        if new_pass != confirm:
            print("Passwords do not match.")
            return
        if len(new_pass) < 8:
            print("Password must be at least 8 characters.")
            return
        reset_password(db, username, new_pass)
    elif choice == "3":
        username = input("Enter new admin username: ").strip()
        if not username:
            print("Username cannot be empty.")
            return
        new_pass = getpass("Enter password: ")
        confirm = getpass("Confirm password: ")
        if new_pass != confirm:
            print("Passwords do not match.")
            return
        if len(new_pass) < 8:
            print("Password must be at least 8 characters.")
            return
        create_admin(db, username, new_pass)
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()