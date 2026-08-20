"""BIS-style portal UI, served by the same process as the API.

Only the shell is rendered server-side. Every figure on the page arrives from
``/api/v1/*`` as the signed-in caller, so the browser can never be handed rows
the metastore would have withheld - there is no server-side render pass that
could accidentally embed a privileged result into the HTML.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

#: Where the "Sign in" button sends a visitor. Databricks Apps has already
#: authenticated them, so it points at the identity endpoint; behind Azure
#: Container Apps the built-in auth route takes over.
SIGN_IN_URL = os.getenv("SOVEREIGNSHIELD_SIGNIN_URL", "/.auth/login/aad?post_login_redirect_uri=/")
SIGN_OUT_URL = os.getenv("SOVEREIGNSHIELD_SIGNOUT_URL", "/.auth/logout?post_logout_redirect_uri=/")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
router = APIRouter()

#: Filter cards, in the order the BIS Data Portal presents them.
FILTER_CARDS = [
    ("parent_country", "Parent country", "L_PARENT_CTY"),
    ("reporting_country", "Reporting country", "L_REP_CTY"),
    ("counterpart_sector", "Counterparty sector", "L_CP_SECTOR"),
    ("counterpart_country", "Counterparty country", "L_CP_COUNTRY"),
    ("currency", "Currency denomination", "L_DENOM"),
    ("position", "Position", "L_POSITION"),
    ("instrument", "Instrument", "L_INSTR"),
]


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def portal(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "portal.html",
        {
            "filter_cards": FILTER_CARDS,
            "sign_in_url": SIGN_IN_URL,
            "sign_out_url": SIGN_OUT_URL,
            "dataflow": "BIS:WS_LBS_D_PUB(1.0)",
        },
    )
