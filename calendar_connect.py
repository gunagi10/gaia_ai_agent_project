# Below code is a template to connect to Google Calendar API v3 using OAuth2, handling token storage and refresh.

import os
import datetime as dt
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_calendar_service():
    """Authenticate (or refresh) and return a Google Calendar v3 service."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            os.remove("token.json")
            return get_calendar_service()

    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save refreshed credentials
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

if __name__ == "__main__":
    service = get_calendar_service()
    me = service.calendarList().get(calendarId="primary").execute()
    print("Connected to calendar:", me.get("summary"), "| ID:", me.get("id"))
