"""Create (or update) the regular Joplin Server user, and rotate the admin
password away from the default.

Idempotent. Logs in at most twice, because the server rate-limits logins.
Quirk: POST /api/users ignores the password, so it has to be set with a
PATCH afterwards (which also clears must_set_password).
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_ADMIN_PASSWORD = "admin"


class ApiError(Exception):
    pass


def call(base, method, path, body=None, session=None):
    req = urllib.request.Request(
        f"{base}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    if session:
        req.add_header("X-API-AUTH", session)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            msg = json.loads(raw).get("error", raw.decode())
        except ValueError:
            msg = raw.decode()
        raise ApiError(f"{method} {path}: HTTP {e.code}: {msg}") from None
    return json.loads(raw) if raw else None


def login(base, email, password):
    return call(base, "POST", "/api/sessions", {"email": email, "password": password})


def main():
    env = os.environ
    base = env["APP_BASE_URL"].rstrip("/")
    admin_email = env.get("JOPLIN_ADMIN_EMAIL", "admin@localhost")
    admin_pw = env["JOPLIN_ADMIN_PASSWORD"]
    user_email = env["JOPLIN_USER_EMAIL"]
    user_pw = env["JOPLIN_USER_PASSWORD"]
    user_name = env.get("JOPLIN_USER_NAME", user_email)

    try:
        sess = login(base, admin_email, admin_pw)
    except ApiError as first:
        if admin_pw == DEFAULT_ADMIN_PASSWORD:
            raise
        # Fresh server: admin still has the default password. Rotate it.
        try:
            sess = login(base, admin_email, DEFAULT_ADMIN_PASSWORD)
        except ApiError:
            raise first from None
        call(base, "PATCH", f"/api/users/{sess['user_id']}",
             {"password": admin_pw}, sess["id"])
        print(f"Admin password for {admin_email} changed to JOPLIN_ADMIN_PASSWORD.")

    if admin_pw == DEFAULT_ADMIN_PASSWORD:
        print("WARNING: admin still uses the default password 'admin'; "
              "set JOPLIN_ADMIN_PASSWORD in .env and rerun.", file=sys.stderr)

    sid = sess["id"]
    users = call(base, "GET", "/api/users", session=sid)["items"]
    user = next((u for u in users if u["email"] == user_email), None)
    if user is None:
        user = call(base, "POST", "/api/users",
                    {"email": user_email, "full_name": user_name}, sid)
        print(f"Created user {user_email}.")
    call(base, "PATCH", f"/api/users/{user['id']}",
         {"password": user_pw, "full_name": user_name,
          "email_confirmed": 1, "must_set_password": 0}, sid)
    print(f"User {user_email} is active with JOPLIN_USER_PASSWORD.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        sys.exit(f"error: {e}")
    except KeyError as e:
        sys.exit(f"error: {e.args[0]} is not set in .env")
