import os
import hashlib
import streamlit as st
import pandas as pd

from src.crawl import crawl_target_timetable
from crawl.db import BUS_TIMELOG


def manager_page():
    st.title("Manager Page")

    # Password gate
    default_env_pwd = os.environ.get("MANAGER_PASSWORD")
    if "__mgr_auth__" not in st.session_state:
        st.session_state["__mgr_auth__"] = False

    if not st.session_state["__mgr_auth__"]:
        with st.form("manager-login", clear_on_submit=False):
            pwd = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
        if submitted:
            # Check env var first (supports plain or hashed)
            if default_env_pwd is not None and verify_password(pwd, default_env_pwd):
                st.session_state["__mgr_auth__"] = True
            else:
                # Fallback to simple local password file
                try:
                    with open("secret/manager_password.txt", "r") as f:
                        file_pwd = f.read().strip()
                    if verify_password(pwd, file_pwd):
                        st.session_state["__mgr_auth__"] = True
                    else:
                        st.error("Invalid password")
                except FileNotFoundError:
                    st.error("Invalid password")

    if not st.session_state["__mgr_auth__"]:
        st.stop()

    st.success("Authenticated")

    # Logout control
    logout_left, logout_right = st.columns([8, 1])
    with logout_right:
        if st.button("Logout"):
            st.session_state["__mgr_auth__"] = False
            st.rerun()

    st.subheader("Password")
    st.caption("Reset the manager password. It will be stored encrypted (PBKDF2-SHA256) in secret/manager_password.txt.")
    with st.form("reset-password", clear_on_submit=True):
        new_pwd = st.text_input("New password", type="password")
        confirm_pwd = st.text_input("Confirm new password", type="password")
        do_reset = st.form_submit_button("Reset password")
    if do_reset:
        if not new_pwd:
            st.error("Password cannot be empty")
        elif new_pwd != confirm_pwd:
            st.error("Passwords do not match")
        else:
            try:
                os.makedirs("secret", exist_ok=True)
                hashed = hash_password(new_pwd)
                with open("secret/manager_password.txt", "w") as f:
                    f.write(hashed)
                try:
                    os.chmod("secret/manager_password.txt", 0o600)
                except Exception:
                    pass
                st.success("Password reset successfully")
            except Exception as e:
                st.exception(e)

    st.subheader("Timetable Update")
    is_vacation = st.toggle("Vacation mode", value=False)

    if st.button("Update timetable now"):
        try:
            crawl_target_timetable(is_vacation=is_vacation)
            st.success("Timetable updated and written under timetable/*.json")
        except Exception as e:
            st.exception(e)

    st.divider()

    st.subheader("Raw Database Browser")
    db = None
    try:
        db = BUS_TIMELOG()
    except Exception as e:
        st.error("Failed to connect DB. Ensure secret/db.yaml exists and DB is reachable.")
        st.stop()

    mode = st.selectbox("Query mode", ["All", "By route_id", "By stop_id", "By vehicle_number"]) 
    arg = None
    if mode != "All":
        arg = st.text_input("Value")

    if st.button("Run query"):
        try:
            if mode == "All":
                rows = db.get_all()
            elif mode == "By route_id":
                rows = db.get_log_by_route_id(arg)
            elif mode == "By stop_id":
                rows = db.get_by_stop_id(arg)
            else:
                rows = db.get_by_vehicle_number(arg)

            if len(rows) == 0:
                st.warning("No rows")
            else:
                df = pd.DataFrame(rows, columns=["idx", "stop_id", "route_id", "route_nm", "vehicle_number", "stop_name"]) if len(rows[0]) == 6 else pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.exception(e)


if __name__ == "__page__":
    manager_page()



# ---- Password helpers ----
def hash_password(password: str) -> str:
    """Create a PBKDF2-SHA256 hash string."""
    iterations = 200000
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored string.

    Supports two formats:
    - Plain text (legacy)
    - PBKDF2-SHA256 in the format: pbkdf2_sha256$iterations$salt_hex$hash_hex
    """
    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, iter_str, salt_hex, hash_hex = stored.split("$")
            iterations = int(iter_str)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
            return computed == expected
        else:
            return password == stored
    except Exception:
        return False

