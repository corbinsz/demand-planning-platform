"""Exchange a ShipHero refresh token for a short-lived access token.

We never ask for or store the ShipHero password. The refresh token is
encrypted at rest and is not returned to the browser.
"""

import httpx

REFRESH_URL = "https://public-api.shiphero.com/auth/refresh"


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    if response.status_code >= 400:
        # Do not include the response body; it can echo the token.
        raise RuntimeError(f"ShipHero refused the refresh token (HTTP {response.status_code}).")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise RuntimeError("ShipHero did not return an access token.")
    return {
        "access_token": token,
        "expires_in": int(data.get("expires_in") or 86400),
    }
