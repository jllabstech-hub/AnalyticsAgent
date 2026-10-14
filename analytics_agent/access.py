"""Authorize validated OIDC identities using a server-owned scope mapping."""
import math
import time
from urllib.parse import urlsplit
from pydantic import ValidationError
from analytics_agent.models import AccessScope


def valid_auth_configuration(auth):
    required = ("redirect_uri","cookie_secret","client_id","client_secret","server_metadata_url")
    if any(not isinstance(auth.get(key),str) or not auth[key].strip() for key in required): return False
    try:
        urls = [urlsplit(auth[key]) for key in ("redirect_uri","server_metadata_url")]
        return (len(auth["cookie_secret"]) >= 32 and all(url.scheme == "https" and url.hostname and not url.username and not url.password for url in urls)
            and not any("REPLACE_" in auth[key] or "YOUR_" in auth[key] for key in required))
    except ValueError: return False


def scope_for_claims(claims, access, now=None):
    """Claims come from st.user after OIDC verification, never from tool arguments."""
    issuer, subject, expiry = claims.get("iss"), claims.get("sub"), claims.get("exp")
    now = time.time() if now is None else now
    if (not isinstance(issuer,str) or not issuer or not isinstance(subject,str) or not subject
        or isinstance(expiry,bool) or not isinstance(expiry,(int,float)) or not math.isfinite(expiry) or expiry <= now):
        raise PermissionError("Sign-in is expired or required identity claims are missing. Sign in again.")
    entry = access.get(f"{issuer}|{subject}")
    if not isinstance(entry,dict) or not {"markets","services","skills"}.issubset(entry):
        raise PermissionError("This account has no approved analytics access.")
    try: scope = AccessScope.model_validate(entry)
    except ValidationError:
        raise PermissionError("This account's access configuration is invalid.") from None
    if not scope.markets or not scope.services or not scope.skills:
        raise PermissionError("This account has no approved analytics access.")
    return scope
