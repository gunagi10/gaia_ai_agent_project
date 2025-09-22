
# 3. This is where all the agent tools are prepped. Includes environment, mongo
# helper settings

import os
from dotenv import load_dotenv
import json
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from pymongo import MongoClient
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults

from calendar_connect import get_calendar_service
from googleapiclient.errors import HttpError

# ─── 1.A) ENV in root folder  ────────────────────────────────── 
load_dotenv() # This reads .env file and sets os.environ

mongo_uri = os.environ["MONGO_URI"]
mongo_db = os.environ["MONGO_DB"]
mongo_coll = os.environ["MONGO_COLL"]
openai_key = os.environ["OPENAI_API_KEY"]
tavily_key = os.environ["TAVILY_API_KEY"]

# ─── 2) SINGLETON MONGO CLIENT ─────────────────────────────────────────────────
# One instance exist in the app to be used everywhere
MONGO_URI = os.environ["MONGO_URI"]
MONGO_DB  = os.environ["MONGO_DB"]
MONGO_COL = os.environ["MONGO_COLL"]
MONGO_CLIENT = MongoClient(MONGO_URI)

# ─── 3) HELPER FUNCTIONS ────────────────────────────────────────────────────────
def load_tax_records() -> pd.DataFrame:
    """
    Pulls all documents from Mongo collection and returns a pandas DataFrame.
    """
    db   = MONGO_CLIENT[MONGO_DB]
    coll = db[MONGO_COL]
    docs = list(coll.find({}, {"_id": 0}))
    return pd.DataFrame(docs)

# Less hassle to identify vancouver timezone later with this variable
VANCOUVER = ZoneInfo("America/Vancouver")

# Summarizer of chatgpt
def _get_summarizer() -> ChatOpenAI:
    return ChatOpenAI(
        model_name="gpt-4o-mini",
        temperature=0.7,
        openai_api_key=os.environ["OPENAI_API_KEY"]
    )

# ─── 4) STREAMLIT SESSION HELPER ────────────────────────────────────────────────

# This is a function that will check who is the verified_user of the chat (source = verification tool)
def _get_verified_user():
    return st.session_state.get("verified_user")

# ─── 5) TOOLS ───────────────────────────────────────────────────────────────────

# A. The verifying user tool
@tool("verify_user", return_direct=False)
def verify_user_tool(name: str, customer_id: str) -> str:
    """
    Verifies the user by matching full name and ID. Stores in session_state.
    """
    # Load mongo DB database to pandas dataframe via load tex record function
    df = load_tax_records()
    
    # Create a mask, compares every row's full name with 'name' input
    mask = (
        df["Full Name"].str.lower() == name.lower()
    ) & (
        df["Customer ID"].astype(str) == customer_id.strip()
    )
    
    # .any() check if any row matched. If no match, return failure message 
    if not mask.any():
        return "❌ I’m sorry, we could not verify your credentials."
        
    # df.loc[mask] means filter to matching rows
    # .iloc[0] means select first match, 
    # .to+dict() means converts into python dictionary
    # This is where the user data is stored in session state for later tools to use
    row = df.loc[mask].iloc[0].to_dict()
    user_data = {"name": row["Full Name"], "id": row["Customer ID"], "row_data": row}

    st.session_state["verified_user"] = user_data
    
    #Reruns normal message with some custom variables in it.
    return (
        f"Hello {row['Full Name']}, you are verified! "
        "You can now ask about your tax record, general queries, or book a meeting."
    )

##B.1. Querying personal tax info with LLM
@tool("query_personal_tax_info", return_direct=False)
def query_personal_tax_info_tool(question: str) -> str:
    """
    Queries the verified user's tax record.
    """
    user = _get_verified_user()
    if not user:
        return "⚠️ Please verify first using your full name and Customer ID."

    df = load_tax_records()
    user_df = df[df["Customer ID"].astype(str) == str(user["id"])]
    if user_df.empty:
        return "❌ Could not find your record. Please verify again."

    record = user_df.iloc[0].to_dict()

    # This is the difference, the tool's logic is now done without ifs logic, and basically just asking the llm
    # LLM can see both query and available row info for the user.
    messages = [
        SystemMessage(content="You are a helpful tax assistant. Answer based on the user's tax record. Be cheerful, positive, and humorous regardless if there are unpaid taxes"),
        HumanMessage(content=f"User asked: {question}\n\nHere is their tax record:\n{record}")
    ]

    # getattr is a python build in function that safely gets obj attribute. 
    # if resp.content exists, return it. if not fallback to str(resp) and give the error message or raw text
    resp = _get_summarizer().invoke(messages)
    return getattr(resp, "content", str(resp))

# C. Search tool with tavily
@tool("search_tool", return_direct=False)
def search_tool(query: str) -> str:
    """
    Pleasantly summarize the search results ahout Canada's attractions and tax related inquiries (regulations, tax consulting offices, accounting firms, etc.)into one concise paragraph while also preserving the original URL or cite the link so user can click and read more
    """
    #a. check if user is verified, reject if not.
    user = _get_verified_user()
    if not user:
        return "⚠️ Please verify first before searching."

    #b. do tavily search. returns json or python list (because the API might get python list or dict, raw json, or error).
    # at this point, raw could be python list, messy string, or error string.
    raw = TavilySearchResults(
        max_results=3,
        api_key=os.environ["TAVILY_API_KEY"]
    ).invoke(query)

    #c. So we try. USE json.loads(raw) if the raw is JSON string and not list (e.g. "["blah"]")
    # if its already python list, just raw (else raw) (e.g. ["blah"])
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw

    #d. if its error message string we dont crash, we show raw error.
    except json.JSONDecodeError:
        return raw

    #e. if still fails, bail out early and return original raw (instead of breaking summarizer)
    if not isinstance(items, list):
        return raw

    #f. Initializing empty list to store individual formatted summaries (1 per result).
    snippets = []
    #g. Looping through list of items. i = index, itm = dictionary; for each result
    for i, itm in enumerate(items, start=1):

        #h. getting title from itm, if its missing give empty. moreover, strip removes whitespace from both ends
        title = itm.get("title", "").strip()
        #i. now do with content. Just replace newline with spaces for cleaner display
        content = itm.get("content", "").replace("\n", " ")
        #j. get url from tavily search
        url = itm.get("url", "").strip() 
        #k. truncation - grab first 200 char. rsplit spilts from last space to avoid cutting words in half
        snippet = content[:200].rsplit(" ", 1)[0] + "…"
        #l. append formatted string like **Canada new tax law - the 2024 update to canada federal tax code includes...
        # added section for url
        snippets.append(
        f"{i}. **[{title}]({url})** — {snippet}"
        if url else
        f"{i}. **{title}** — {snippet}"
    )
    #m. joins all strings with double newlines between them. to send to llm to be summarized
    raw_block = "\n\n".join(snippets)
    #n. just using langchain's way of invoking llm. Ask it to preserve url. it works, but maybe tavily is a bit too simple? the url leads to homepage only.
    system = SystemMessage(content="""
    Pleasantly summarize the following search results into one concise paragraph while also preserving the original URL or cite the link so user can click and read more""")
    human  = HumanMessage(content=raw_block)
    resp   = _get_summarizer().invoke([system, human])
    return getattr(resp, "content", str(resp))

#D. Create booking with google calendar TOOL
@tool("create_booking", return_direct=False)
def create_booking_tool(date_time: str, meeting_topic: str) -> str:
    """
    Creates a new booking on Google Calendar for the verified user.
    When you call this tool, you must:

    1. **Extract** the date and time from the user’s sentence (e.g. “19 May 2025 at 12 PM”)  
    2. **Reformat** it into the exact ISO format **YYYY-MM-DD HH:MM** (24-hour clock, America/Vancouver)  
    3. **Pass** that string as the first argument, and a brief meeting topic string as the second.

    **Example**  
    If the user says:  
    > “Book meeting 19 May 2025, 12 PM about my son’s taxes”  

    You should invoke:  
    create_booking("2025-05-19 12:00", "my son’s taxes")
    Remember to always provide the download ics file as a clickable format when outputting answers.
    This part below -> [Download .ics file](data:text/calendar;base64,{b64})
    """
# User must be verified
    user = _get_verified_user()
    if not user:
        return "❌ You are not verified. Please verify before booking."

# Parse and validate datetime (changing the format so it can be understood) and validate
# user input (after parse) must match format.
    try:
        booking_dt = dt.datetime.strptime(date_time, "%Y-%m-%d %H:%M").replace(tzinfo=VANCOUVER)
    except ValueError:
        return "Invalid format – use YYYY-MM-DD HH:MM (24h, Vancouver)."

# rules of booking time. not in the past, not more than 365 days, not on weekends, not outside business hours. 30 mins increment)
    now = dt.datetime.now(VANCOUVER)
    if booking_dt < now:
        return "Cannot book in the past."
    if booking_dt > now + dt.timedelta(days=365):
        return "Please choose a date within one year."
    if booking_dt.weekday() >= 5:
        return "Bookings only Monday–Friday."

    minute = 30 if booking_dt.minute >= 30 else 0
    booking_dt = booking_dt.replace(minute=minute, second=0, microsecond=0)
    if not (9 <= booking_dt.hour < 16 or (booking_dt.hour == 16 and booking_dt.minute == 0)):
        return "Business hours: 09:00–16:00 in 30-min increments."

# Connect to Google Calendar - we prepared the function in calendar_connect.py
    service = get_calendar_service()

# Get all events for the chosen day (purpose - to check if slot already taken)
    booking_date = booking_dt.date()
    start_of_day = dt.datetime.combine(booking_date, dt.time.min, tzinfo=VANCOUVER)
    end_of_day   = dt.datetime.combine(booking_date, dt.time.max, tzinfo=VANCOUVER)
    try:
        resp = service.events().list(
            calendarId="primary",
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = resp.get("items", [])
    except HttpError as e:
        return f"Error retrieving events: {e}"

# for every event, parse and compare to desired time
    busy = []
    for ev in events:
        dt_str = ev["start"].get("dateTime") or ev["start"].get("date")
        try:
            ev_dt = dt.datetime.fromisoformat(dt_str)
            busy.append(ev_dt.time())
        except ValueError:
            continue
#Checking slot conflict either business window or no one booked at that time.
    desired_time = booking_dt.time()
    allowed      = [dt.time(h, m) for h in range(9, 17) for m in (0, 30)]
    if desired_time not in allowed:
        return "❌ Business hours are 09:00–16:00 in 30‑min increments."
    if desired_time in busy:
        return "😔 I’m sorry, that slot is already taken—please choose another time."
        
# Book the event (fixed to 20 mins)
    booking_end = booking_dt + dt.timedelta(minutes=20)
    event = {
        "summary": f"{user['id']}, {user['name']}, Meeting with tax advisor",
        "description": meeting_topic,
        "start": {"dateTime": booking_dt.isoformat(), "timeZone": "America/Vancouver"},
        "end":   {"dateTime": booking_end.isoformat(), "timeZone": "America/Vancouver"},
    }

    # Insert the event. if success return the confirmation message and link. If not say its error.

    try:
        created = service.events().insert(calendarId="primary", body=event).execute()
        when = booking_dt.strftime("%Y-%m-%d %I:%M %p")

        # Generate ICS and embed as data URI link.
        from ics import Calendar, Event
        import base64


        cal = Calendar()
        ev  = Event()
        ev.name        = "Meeting with Gian (tax advisor) - Arranged by GAIA"
        ev.begin       = booking_dt
        ev.end         = booking_end
        ev.description = meeting_topic
        cal.events.add(ev)
        ics_content = cal.serialize()
        b64 = base64.b64encode(ics_content.encode()).decode()

        # one string, markdown link included
        return (
            f"✅ Booking confirmed for **{when}**!  \n\n"
            f"[Download .ics file](data:text/calendar;base64,{b64})  \n\n"
            "Click that link to pull this meeting into your calendar."
        )
    except HttpError as e:
        return f"❌ Error creating booking: {e}"

# 🔧 Utility function to handle both string and datetime inputs safely
def parse_datetime(input_val):
    """
    Converts input to a timezone-aware datetime object.
    Accepts:
      • string in "YYYY-MM-DD HH:MM" format, or
      • a datetime.datetime object
    Raises a clear error otherwise.
    """
    if isinstance(input_val, dt.datetime):
        return input_val.astimezone(VANCOUVER)
    if isinstance(input_val, str):
        try:
            return dt.datetime.strptime(input_val.strip(), "%Y-%m-%d %H:%M") \
                      .replace(tzinfo=VANCOUVER)
        except ValueError:
            raise ValueError("Invalid datetime string. Use format YYYY-MM-DD HH:MM.")
    raise TypeError("Datetime input must be string or datetime object.")


# E. Next tool to list, cancel, or reschedule your bookings.
#    False to enable agent answering return in a human natured language
@tool("update_booking", return_direct=False)
def update_booking_tool(original_datetime: str = "", new_datetime: str = "") -> str:
    """
    Manage your existing bookings. There are three behaviors:

    1️. **List**  
      If you call **with no arguments** (`original_datetime=None`), I'll list all future bookings.

    2️. **Cancel**  
      If you supply only original_datetime and `new_datetime="cancel"`, I'll delete that booking.

    3️. **Reschedule**  
      If you supply both original_datetime and new_datetime, I'll move the booking.
    """

    #1. Check if user is verified
    user = st.session_state.get("verified_user")
    if not user:
        return "❌ You are not verified. Please verify first before updating bookings."

    #2. Get calendar service
    svc = get_calendar_service()
    
    #3. Fetch all future events
    now_iso = dt.datetime.now(VANCOUVER).isoformat()
    try:
        resp = svc.events().list(
            calendarId="primary",
            timeMin=now_iso,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        items = resp.get("items", [])
    except HttpError as e:
        return f"Error fetching events: {e}"

    #4. Filter events belonging to this user
    prefix = f"{user['id']}, {user['name']}"
    your_events = [ev for ev in items if ev.get("summary", "").startswith(prefix)]
    if not your_events:
        return "You have no upcoming bookings."

    #5. Branch 1: List bookings if no original_datetime supplied
    if not original_datetime:
        lines = []
        for ev in your_events:
            sd = ev["start"].get("dateTime") or ev["start"].get("date")
            dt_obj = dt.datetime.fromisoformat(sd).astimezone(VANCOUVER)
            desc   = ev.get("description", "No description provided")
            lines.append(f"- {dt_obj.strftime('%Y-%m-%d %H:%M')} - Topic: {desc}")
        return (
            "📋 Your upcoming bookings:\n" + "\n".join(lines) +
            "\n\nTo cancel: update_booking(original_datetime=\"YYYY-MM-DD HH:MM\", new_datetime=\"cancel\")" +
            "\nTo reschedule: update_booking(original_datetime=\"…\", new_datetime=\"YYYY-MM-DD HH:MM\")"
        )

    #6. Branch 2: Cancel or reschedule
    #7. Parse the requested original_datetime
    try:
        orig_dt = parse_datetime(original_datetime)
    except (ValueError, TypeError) as e:
        return f"❌ Couldn’t parse original_datetime: {e}"

    #8. Find the event matching the original_datetime exactly
    target = None
    for ev in your_events:
        sd = ev["start"].get("dateTime")
        if not sd:
            continue
        ev_start = dt.datetime.fromisoformat(sd).astimezone(VANCOUVER) \
                      .replace(second=0, microsecond=0)
        if ev_start == orig_dt:
            target = ev
            break
    if not target:
        return f"No booking found at {original_datetime}."

    event_id = target["id"]

    #9. Branch 2A: Cancel booking if new_datetime is empty or "cancel"
    if not new_datetime or new_datetime.strip().lower() == "cancel":
        try:
            svc.events().delete(calendarId="primary", eventId=event_id).execute()
            return f"✔️ Your booking on {original_datetime} has been cancelled."
        except HttpError as e:
            return f"Error cancelling booking: {e}"

    #10. Branch 2B: Reschedule. Parse new_datetime, enforce rules
    try:
        new_dt = parse_datetime(new_datetime)
    except (ValueError, TypeError) as e:
        return f"❌ Couldn’t parse new_datetime: {e}"

    if new_dt.weekday() >= 5:
        return "❌ Bookings only allowed Monday–Friday."
    # Snap to nearest 30-minute slot
    minute = 30 if new_dt.minute >= 30 else 0
    new_dt = new_dt.replace(minute=minute, second=0, microsecond=0)
    if not (9 <= new_dt.hour < 16 or (new_dt.hour == 16 and new_dt.minute == 0)):
        return "❌ Business hours are 09:00–16:00 in 30-min increments."

    #11. Check overlap (if new slot is free)
    booking_date = new_dt.date()
    start_of_day = dt.datetime.combine(booking_date, dt.time.min, tzinfo=VANCOUVER)
    end_of_day   = dt.datetime.combine(booking_date, dt.time.max, tzinfo=VANCOUVER)
    resp = svc.events().list(
        calendarId="primary",
        timeMin=start_of_day.isoformat(),
        timeMax=end_of_day.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    all_events = resp.get("items", [])

    occupied = set()
    for ev in all_events:
        if ev["id"] == event_id:
            continue
        sd = ev["start"].get("dateTime")
        if not sd:
            # skip all-day or date-only events
            continue
        # parse ISO string → local datetime → truncate seconds/microseconds → get .time()
        t = dt.datetime.fromisoformat(sd) \
               .astimezone(VANCOUVER) \
               .replace(second=0, microsecond=0) \
               .time()
        occupied.add(t)

    if new_dt.time() in occupied:
        return "😔 I’m sorry, there is already a booking at that time—please try another slot."

    #12. Finally, patch the event to the new slot
    new_end = new_dt + dt.timedelta(minutes=20)
    body = {
        "start": {"dateTime": new_dt.isoformat(), "timeZone": "America/Vancouver"},
        "end":   {"dateTime": new_end.isoformat(), "timeZone": "America/Vancouver"},
    }
    try:
        svc.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
        return f"✔️ Your booking has been moved to {new_datetime}."
    except HttpError as e:
        return f"Error updating booking: {e}"
