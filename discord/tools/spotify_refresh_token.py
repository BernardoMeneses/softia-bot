from __future__ import annotations

import base64
import json
import os
import secrets
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-read-private playlist-read-collaborative"


def main() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path)

    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()

    if not client_id or not client_secret:
        raise SystemExit("Define SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env primeiro.")

    state = secrets.token_urlsafe(16)
    auth_url = _authorization_url(client_id, redirect_uri, state)

    print("Abre este URL no browser e autoriza a app:\n")
    print(auth_url)
    print()
    print(
        "Depois de autorizar, copia o URL COMPLETO da barra do browser para aqui. "
        "Nao coloques esse URL nem o valor de code= no .env."
    )
    callback_or_code = input("URL final: ").strip()
    code, returned_state = _read_code(callback_or_code)

    if returned_state and returned_state != state:
        raise SystemExit("State recebido nao corresponde ao state enviado. Cancela e tenta outra vez.")

    refresh_token = _exchange_code_for_refresh_token(client_id, client_secret, redirect_uri, code)
    _upsert_env_value(env_path, "SPOTIFY_REFRESH_TOKEN", refresh_token)
    print("\nColoca exatamente esta linha no teu .env:\n")
    print(f"SPOTIFY_REFRESH_TOKEN={refresh_token}")
    print(f"\nTambem atualizei automaticamente: {env_path}")


def _authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "state": state,
        }
    )
    return f"{SPOTIFY_AUTHORIZE_URL}?{query}"


def _read_code(callback_or_code: str) -> tuple[str, str | None]:
    if not callback_or_code.startswith(("http://", "https://")):
        return callback_or_code, None

    parsed = urllib.parse.urlparse(callback_or_code)
    params = urllib.parse.parse_qs(parsed.query)
    error = params.get("error", [""])[0]
    if error:
        raise SystemExit(f"Spotify devolveu erro: {error}")

    code = params.get("code", [""])[0]
    if not code:
        raise SystemExit("Nao encontrei `code` no URL final.")

    state = params.get("state", [""])[0] or None
    return code, state


def _exchange_code_for_refresh_token(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> str:
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        SPOTIFY_TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"Nao consegui trocar o code pelo refresh token: {exc}") from exc

    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not refresh_token:
        raise SystemExit("Spotify nao devolveu refresh_token. Confirma o redirect URI e tenta outra vez.")

    return refresh_token


def _upsert_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replacement = f"{key}={value}"
    replaced = False

    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = replacement
            replaced = True
            break

    if not replaced:
        lines.append(replacement)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
