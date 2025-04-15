"""Constants for pybticino."""

import base64

# Base URL for the Netatmo API
BASE_URL = "https://app.netatmo.net"

# OAuth2 endpoints
TOKEN_ENDPOINT = "/oauth2/token"

# Client credentials (obfuscated using Base64)
_ENCODED_CLIENT_ID = "bmFfY2xpZW50X2FuZHJvaWRfd2VsY29tZQ=="
_ENCODED_CLIENT_SECRET = "OGFiNTg0ZDYyY2EyYTc3ZTM3Y2NjNmIyYzdlNGYyOWU="


def get_client_id():
    """Return the Base64 decoded client ID."""
    try:
        # Ensure correct padding if needed, though standard encoding usually handles it
        return base64.b64decode(_ENCODED_CLIENT_ID).decode("utf-8")
    except Exception as e:
        # Log error or raise a specific exception if decoding fails
        print(f"Error decoding client ID: {e}")  # Replace with proper logging/exception
        return ""


def get_client_secret():
    """Return the Base64 decoded client secret."""
    try:
        return base64.b64decode(_ENCODED_CLIENT_SECRET).decode("utf-8")
    except Exception as e:
        print(
            f"Error decoding client secret: {e}"
        )  # Replace with proper logging/exception
        return ""


# Default scope (from logs)
DEFAULT_SCOPE = "security_scopes"

# Default App Version (from logs)
DEFAULT_APP_VERSION = "4.1.1.3"
# Default Build Number (from logs User-Agent)
DEFAULT_BUILD_NUMBER = "4401103"
# Default Android Version (from logs User-Agent)
DEFAULT_ANDROID_VERSION = "13"
# Default Device Info (from logs User-Agent)
DEFAULT_DEVICE_INFO = "Google/sdk_gphone64_arm64"
# Default Platform (from logs Subscribe message)
DEFAULT_PLATFORM = "Android"


def build_user_agent(
    app_version=DEFAULT_APP_VERSION,
    build_number=DEFAULT_BUILD_NUMBER,
    android_version=DEFAULT_ANDROID_VERSION,
    device_info=DEFAULT_DEVICE_INFO,
):
    """Build the User-Agent string based on components."""
    # Format based on observed User-Agent:
    # NetatmoApp(Security/v4.1.1.3/4401103) Android(13/Google/sdk_gphone64_arm64)
    return (
        f"NetatmoApp(Security/v{app_version}/{build_number}) "
        f"Android({android_version}/{device_info})"
    )


# API Endpoints
HOMESDATA_ENDPOINT = "/api/homesdata"
HOMESTATUS_ENDPOINT = "/syncapi/v1/homestatus"
SETSTATE_ENDPOINT = "/syncapi/v1/setstate"
GETEVENTS_ENDPOINT = (
    "/api/getevents"  # Note: Log shows /%2Fapi%2Fgetevents, using decoded path
)
ADD_PUSH_CONTEXT_ENDPOINT = "/api/addpushcontext"
MODIFY_USER_ENDPOINT = "/api/modifyuser"
GET_HOME_USERS_ENDPOINT = "/api/gethomeusers"
UPDATE_SESSION_ENDPOINT = "/api/updatesession"

# Other hosts / WS URLs
# WS_HOST = "app-ws.netatmo.net" # Keep original host if needed elsewhere, or remove
PUSH_WS_URL = "wss://app-ws.netatmo.net/ws/"  # For push notifications (app_camera)
RTC_WS_URL = "wss://app.netatmo.net/appws/"  # For WebRTC signaling (app_security)
NEWS_HOST = "api-news.netatmo.net"
