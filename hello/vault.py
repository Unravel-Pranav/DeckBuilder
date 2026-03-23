import os
import time
from typing import Dict, Optional, Tuple
import hvac
import logging

logger = logging.getLogger(__name__)


def get_secrets(host_addr, token, path, max_retries=3):
    """
    Fetch secrets stored in HashiCorp Vault with retry logic.

    Args:
        host_addr (str): Vault server address.
        token (str): Vault authentication token.
        path (str): Path to the secret in Vault.
        max_retries (int): Maximum number of retry attempts.

    Returns:
        dict: Secrets as a dictionary, or None if not found.
    Raises:
        Exception: If unable to fetch secrets after retries.
    """
    client = hvac.Client(url=host_addr, token=token)
    is_authenticated = client.is_authenticated()
    logger.info("Vault authentication successful=%s", is_authenticated)
    logger.info("Fetching secret path: %s", path)

    # Check authentication first
    if not is_authenticated:
        return None

    for retry_count in range(1, max_retries + 1):
        try:
            # This call resulting to Permission Denied, so using different approach
            #secret = client.secrets.kv.v2.read_secret_version(path=path)
            # Using the older API method
            secret = client.read(path)
            logger.debug("Vault secret fetched for path %s", path)
            if not secret or "data" not in secret or "data" not in secret["data"]:
                return None
            secrets_data = secret["data"]["data"]
            return secrets_data
        except Exception as err:
            err_str = str(err)
            err_type = type(err).__name__

            if "timeout" in err_str:
                time.sleep(10)
            elif "permission denied" in err_str:
                return None
            else:
                return None
    raise Exception(f"Vault secret fetch failed after {max_retries} attempts.")

def set_env(key, val):
    """
    Sets an environment variable if not already set.
    """
    if os.getenv(key) is None:
        try:
            os.environ[key] = str(val)
        except Exception as e:
            logger.error("Failed to set environment variable %s: %s", key, e)
    else:
        logger.debug("Environment variable %s already set", key)

def load_vault_secrets():
    """
    Loads secrets from HashiCorp Vault and sets them as environment variables.
    """
    # Get required Vault configuration
    host = os.getenv("VAULT_ADDR")
    token_path = os.getenv("VAULT_TOKEN")
    if not host or not token_path:
        return

    # try:
    #     # Testing path - DEV
    #     # token_path = '/Users/PVarma/Documents/dev-vault-token.log'
    #     with open(token_path, "r") as f:
    #         dat = f.read()
    # except Exception as e:
    #     err_type = type(e).__name__
    #     err_msg = str(e)
    #     print(err_msg)
    #     return e

    # if not dat:
    #     print('not valult token')
    #     return

    # token = dat.strip()
    path = os.getenv("VAULT_SECRETS_ROOT")
    project = os.getenv("VAULT_PROJECT_NAME")
    logger.info("Vault secrets root/path: %s", path)
    logger.info("Vault project name: %s", project)

    # if not path or not project:
    #     missing_config = [] if path and project else (["VAULT_SECRETS_ROOT"] if not path else []) + (["VAULT_PROJECT_NAME"] if not project else [])
        
    #     return Exception("Incomplete Vault configuration")

    # Load secrets using project and source (default to edp)
    secret_path = f"{path}/{project}".lower()
    logger.info("Resolved Vault secret path: %s", secret_path)
    token  = os.getenv('VAULT_TOKEN')
    logger.debug("Vault token detected: %s", bool(token))

    # Use the path we constructed for getting secrets
    vals = get_secrets(host, token, secret_path)
    if vals:
        logger.info("Retrieved %d secret(s) from Vault", len(vals))
        logger.debug("Vault secret keys: %s", list(vals.keys()))

    return None


def print_vault_token(env:str, *, mount_path: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Fetch and print Vault secrets using the token mounted in the pod."""
    # Map environment to mount path
    mount_path_map = {
        "dev": "/secure-mount-point/.secrets/dev",
        "qa": "/secure-mount-point/.secrets/qa",
        "prod": "/secure-mount-point/.secrets/prod",
    }
    default_mount = mount_path_map.get(env, "/secure-mount-point/.secrets/dev")
    mount_path = mount_path or default_mount
    VAULT_ADDR="https://lockbox.gcso.cbre.com"
    VAULT_SECRETS_ROOT=f"dt-data/denali/{env}/kv/data" 
    VAULT_PROJECT_NAME="market_reports/edp"

    host = VAULT_ADDR
    root = VAULT_SECRETS_ROOT
    project = VAULT_PROJECT_NAME

    if not all([host, root, project]):
        logger.error("Vault configuration missing required environment variables.")
        return None

    try:
        if not os.path.isdir(mount_path):
            logger.error("Vault token mount path not found: %s", mount_path)
            return None

        token_file = os.path.join(mount_path, '.vault_token')


        if not token_file:
            logger.error("No token file present in %s", mount_path)
            return None

        with open(token_file, "r", encoding="utf-8") as file_handle:
            token = file_handle.read().strip()

        if not token:
            logger.error("Token file %s is empty.", token_file)
            return None

        secret_path = f"{root}/{project}".lower()
        secrets = get_secrets(host, token, secret_path)

        if not secrets:
            logger.error("Failed to fetch secrets from Vault.")
            return None

        
        return secrets

    except Exception as exc:
        logger.exception("Error while fetching Vault secrets: %s", exc)
        return None



def _split_mount_and_path(full_path: str) -> Tuple[str, str]:
    """
    Split a 'mount/rel/path' into ('mount', 'rel/path').
    Example: 'secret/myproj/edp' -> ('secret', 'myproj/edp')
    """
    parts = full_path.strip("/").split("/", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]

def _kv_version(client: hvac.Client, mount_point: str) -> int:
    """
    Detect whether a KV engine at mount_point is v1 or v2.
    Falls back to v1 if detection fails.
    """
    try:
        tune = client.sys.read_mount_configuration(path=mount_point)
        opts = (tune or {}).get("data", {}).get("options", {})
        return 2 if str(opts.get("version", "1")) == "2" else 1
    except Exception:
        return 1

def put_secrets(
    host_addr: str,
    token: str,
    full_path: str,
    values: Dict[str, str],
    *,
    cas: Optional[int] = None,
    patch: bool = False,
) -> Dict:
    """
    Write secrets to Vault at `full_path` (e.g. 'secret/myproj/edp').

    - KV v2:
        - By default, create_or_update_secret REPLACES the entire dict at that path.
        - Use patch=True to merge only the provided keys (partial update).
        - Use cas=<version> for check-and-set.
    - KV v1: create_or_update_secret writes the dict at that path.
    """
    client = hvac.Client(url=host_addr, token=token)
    if not client.is_authenticated():
        raise RuntimeError("Vault authentication failed")

    mount_point, rel_path = _split_mount_and_path(full_path)
    if not rel_path:
        raise ValueError("Secret path must include a relative path after the mount point")

    version = _kv_version(client, mount_point)

    if version == 2:
        if patch:
            # Partial update: merges keys without replacing the whole dict
            return client.secrets.kv.v2.patch(
                path=rel_path, mount_point=mount_point, secret=values
            )
        else:
            # Full replace (send ALL keys you want to keep), supports CAS
            return client.secrets.kv.v2.create_or_update_secret(
                path=rel_path, mount_point=mount_point, secret=values, cas=cas
            )
    else:
        # KV v1 has no patch; always full replace
        return client.secrets.kv.v1.create_or_update_secret(
            path=rel_path, mount_point=mount_point, secret=values
        )

def write_vault_secrets_from_env(extra: Optional[Dict[str, str]] = None, patch: bool = False):
    """
    Convenience wrapper that mirrors your loader's env layout.
    Expects:
      VAULT_ADDR, VAULT_TOKEN, VAULT_SECRETS_ROOT, VAULT_PROJECT_NAME
    Writes to:  {VAULT_SECRETS_ROOT}/{VAULT_PROJECT_NAME}/edp
    """
    host = os.getenv("VAULT_ADDR")
    token = os.getenv("VAULT_TOKEN")
    root  = os.getenv("VAULT_SECRETS_ROOT")
    project = os.getenv("VAULT_PROJECT_NAME")
    if not all([host, token, root, project]):
        raise RuntimeError("Missing one of VAULT_ADDR / VAULT_TOKEN / VAULT_SECRETS_ROOT / VAULT_PROJECT_NAME")

    secret_path = f"{root}/{project}/edp".lower()

    # Example payload (merge with caller-provided extras)
    payload = {
        "DB_HOST": "db.example.internal",
        "DB_USER": "svc_user",
        "DB_PASS": "super-secret",
    }
    if extra:
        payload.update(extra)

    return put_secrets(
        host_addr=host,
        token=token,
        full_path=secret_path,
        values=payload,
        patch=patch,   # set True to merge keys on KV v2
        cas=None,      # e.g. set to the expected current version for CAS writes
    )

if __name__ == "__main__":

    load_vault_secrets()
    
    # resp = write_vault_secrets_from_env(
    #     extra={"API_KEY": "abcd-1234"},
    #     patch=True  # partial update on KV v2; harmless on KV v1 (falls back to full write)
    # )
    # print(resp)
