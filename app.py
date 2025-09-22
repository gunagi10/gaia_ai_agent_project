import streamlit as st
# 1) Page config MUST be first Streamlit command
st.set_page_config(page_title="Gian's AI Agent", layout="wide")
# 2) Now it's safe to read secrets and set env
import os
from dotenv import load_dotenv
load_dotenv() 

# Best practice to avoid raising error when no key is there, ensure doesnt print on note, keeps langsmith working silently under hood
langsmith_key = os.environ.get("LANGSMITH_API_KEY", "")
if langsmith_key:
    os.environ["LANGSMITH_API_KEY"] = langsmith_key
    os.environ["LANGSMITH_TRACING"] = os.environ.get("LANGSMITH_TRACING", "true")
else:
    st.warning("⚠️ LangSmith key not found — tracing is OFF.")

# 3) All other imports
from agent_tools import load_tax_records
from agent_core import model, tools, system_message, ChatSession
from langgraph.checkpoint.memory import MemorySaver
from pymongo import MongoClient
import uuid
import openai
from whisper import whisper_stt
import base64
import re

MONGO_URI  = os.environ["MONGO_URI"]
MONGO_DB   = os.environ["MONGO_DB"]
MONGO_COLL = os.environ["MONGO_COLL"]
openai.api_key = os.environ["OPENAI_API_KEY"]

# for voice replies
def tts_audio(text, voice="nova"):                  # voice choices: alloy, echo, fable, onyx, nova, shimmer
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"]) 
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",  
        voice=voice,    
        input=text,
    )
    audio_data = response.content  # raw MP3 bytes
    b64 = base64.b64encode(audio_data).decode()
    audio_html = f'<audio controls autoplay src="data:audio/mp3;base64,{b64}"></audio>'
    return audio_html

# Helper function so links are just text

def strip_markdown_links(text):
    """
    Replace all [text](url) markdown links with just 'text'.
    If the link is a data URI (e.g., .ics download), remove it entirely or replace with a short phrase.
    """
    # Remove .ics download links in markdown
    text = re.sub(r'\[([^\]]+)\]\(data:text/calendar[^)]*\)', 'Calendar invite as attached', text)
    # Remove bare .ics data URIs (not in markdown)
    text = re.sub(r'data:text/calendar[^)\s]*', 'Calendar invite as attached', text)
    # Replace all other markdown links with just their text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text

# --- NAVIGATION ---
page = st.sidebar.radio(
    "Navigation",
    ["🤖 Client - Text Chat with GAIA", "🎤 Client - Voice Chat with GAIA (experimental)" , "🛠️ Admin - Add Record", "⚙️ Admin - Manage Records"]
)

# --- LOGIN GATE: Initialize login flag ---
if page in ["🛠️ Admin - Add Record", "⚙️ Admin - Manage Records", "🎤 Client - Voice Chat with GAIA (experimental)"]:
    # im creating a new session variable (logged_in). If "logged_in is not in this session state, add it and
    # set it to false.
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    def show_login():
        st.markdown(
            """
            <div style='background-color:#111; padding:2rem; border-radius:8px;
                        color:#eee; max-width:400px; margin:auto;'>
              <h2>🔒 Admin Log In</h2>
            """, unsafe_allow_html=True)

        with st.form(key="login_form"):
            name      = st.text_input("Full Name", value="Insert admin's credentials")
            cid       = st.text_input("Customer ID", type="password", value="")
            submitted = st.form_submit_button("Log In")

        if submitted:
            # Hardcoded check
            if name == "admin" and cid == "administrator":
                st.session_state["logged_in"]   = True
                st.session_state["user_name"]   = name
                st.session_state["customer_id"] = cid
            else:
                st.error("❌ Invalid credentials. Please ask admin for access.")

        st.markdown("</div>", unsafe_allow_html=True)

    if not st.session_state["logged_in"]:
        show_login()
        st.stop()

# --- ADD TAX RECORD ---
if page == "🛠️ Admin - Add Record":
    st.title("➕ Add a New Tax Record")
    with st.form(key="new_record_form"):
        full_name    = st.text_input("Full Name")
        customer_id  = str(uuid.uuid4())[:8]
        st.markdown(f"**Generated Customer ID (after click submit):** `{customer_id}`")
        
        total_income = st.number_input("Total Income", min_value=0, step=100)
        deductions   = st.number_input("Deductions", min_value=0, step=100)

        # --- derived fields ---
        taxable_income = total_income - deductions
        st.markdown(f"**Taxable Income:** {taxable_income:,}")

        TAX_RATE = 0.15
        tax_due = taxable_income * TAX_RATE
        st.markdown(f"**Tax Due (@ {TAX_RATE*100:.0f}%):** {tax_due:,.2f}")

        tax_paid   = st.number_input("Tax Paid", min_value=0, step=100)
        refund_bal = tax_paid - tax_due
        st.markdown(f"**Refund / Balance:** {refund_bal:,.2f}")

        submitted = st.form_submit_button("Submit Record")

    if submitted:
        client = MongoClient(MONGO_URI)
        db     = client[MONGO_DB]
        coll   = db[MONGO_COLL]

        # left is my db column names, right are the variable name for streamlit form
        coll.insert_one({
            "Full Name":      full_name,
            "Customer ID":    customer_id,
            "Total Income":   total_income,
            "Deductions":     deductions,
            "Taxable Income": taxable_income,
            "Tax Due":        tax_due,
            "Tax Paid":       tax_paid,
            "Refund/Balance": refund_bal
        })
        st.success("✅ New tax record added! It may now chat with GAIA and it will be personalized!")

# --- MANAGE TAX RECORDS ---
elif page == "⚙️ Admin - Manage Records":
    st.title("⚙️ Manage Tax Records")
    df = load_tax_records()
    st.dataframe(df)
    cust_ids = df["Customer ID"].astype(str).tolist()
    selected = st.selectbox("Select Customer ID to manage", [""] + cust_ids)
    if selected:
        record = df[df["Customer ID"].astype(str) == selected].iloc[0].to_dict()
        with st.form(key="edit_record_form"):
            fn = st.text_input("Full Name", value=record["Full Name"])
            ci = st.text_input("Customer ID", value=str(record["Customer ID"]))
            ti = st.number_input("Total Income", value=int(record.get("Total Income",0)))
            dd = st.number_input("Deductions", value=int(record.get("Deductions",0)))
            txi= st.number_input("Taxable Income", value=int(record.get("Taxable Income",0)))
            txd= st.number_input("Tax Due", value=int(record.get("Tax Due",0)))
            txp= st.number_input("Tax Paid", value=int(record.get("Tax Paid",0)))
            rf = st.number_input("Refund/Balance", value=int(record.get("Refund/Balance",0)))
            save   = st.form_submit_button("Save Changes")
            delete = st.form_submit_button("Delete Record")
        client = MongoClient(MONGO_URI)
        db     = client[MONGO_DB]
        coll   = db[MONGO_COLL]
        if save:
            coll.update_one(
                {"Customer ID": selected},
                {"$set":{
                    "Full Name": fn,
                    "Customer ID": ci,
                    "Total Income": ti,
                    "Deductions": dd,
                    "Taxable Income": txi,
                    "Tax Due": txd,
                    "Tax Paid": txp,
                    "Refund/Balance": rf
                }}
            )
            st.success(f"✅ Updated record for {ci}.")
        if delete:
            coll.delete_one({"Customer ID": selected})
            st.success(f"🗑️ Deleted record for {selected}.")

# --- VOICE CHATBOT UI ---
elif page == "🎤 Client - Voice Chat with GAIA (experimental)":
    st.title("🎤 Voice Chat with GAIA (experimental)")

    st.info("Click 'Start recording', ask your question, then click 'Stop'. GAIA will reply with voice. Previous questions and answers are shown below as text.")

    # Record and transcribe audio
    voice_text = whisper_stt(language="en", key="voice_chat")

    if voice_text:
        st.success(f"🗣️ Transcribed: {voice_text}")

        # Send to GAIA agent and get response
        response = st.session_state.chat.send(voice_text)

        # Save history (init if not exists)
        if "voice_history" not in st.session_state:
            st.session_state.voice_history = []

        st.session_state.voice_history.append((voice_text, response))

        # Play the latest response as audio
        st.markdown("**GAIA's Response (Audio):**")
        tts_input = strip_markdown_links(response)
        st.markdown(tts_audio(tts_input), unsafe_allow_html=True)
        st.info("You can ask another question below.")

    # Show text Q&A history (no audio, no replay buttons)
    if st.session_state.get("voice_history"):
        with st.expander("📝 Previous Voice Q&A"):
            for i, (q, a) in enumerate(reversed(st.session_state.voice_history)):
                st.markdown(f"**Q{len(st.session_state.voice_history)-i}:** {q}")
                st.markdown(f"**A{len(st.session_state.voice_history)-i}:** {a}")


# --- CHATBOT (GAIA) UI ---

else:

    # GAIA UI
    st.title("🤖 Gian’s AI Agent (GAIA)")
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    st.write(f"🆔 Current thread id: {st.session_state.thread_id}")
    st.markdown(
        f"""
        **Welcome!**  
        Hi, I’m GAIA.  
        Here’s what I can help you with:
        1. ✅ Look up your personal tax record in our database (Your total income, deductions taxable income, tax due, tax paid, and refund information!).
        2. 🔎 Answer Canada's general tax questions and attractions.
        3. 📅 Book or update a consultation slot with Mr. Gian, our tax advisor.  
        Just type below and press Enter to chat. Or, you can press record and stop record for our voice transcription feature😎.
        """
    )


        # ─── session‐scoped memory & agent ─────────────────────────────
    if "memory" not in st.session_state:
        from langgraph.checkpoint.memory import MemorySaver
        st.session_state["memory"] = MemorySaver()

    if "agent" not in st.session_state:
        from agent_core import create_react_agent, model, tools
        st.session_state["agent"] = create_react_agent(
            model,
            tools,
            checkpointer=st.session_state["memory"],
        )

    # ─── now pass THIS session's agent into ChatSession ──────────
    if "chat" not in st.session_state:
        st.session_state.chat = ChatSession(
            st.session_state["agent"],
            system_message
        )
        st.session_state.past      = []
        st.session_state.generated = []


    def _on_enter():
        txt = st.session_state.user_input.strip()
        if not txt:
            return
        resp = st.session_state.chat.send(txt)
        st.session_state.past.append(txt)
        st.session_state.generated.append(resp)
        st.session_state.user_input = ""
    
    for u, b in zip(st.session_state.past, st.session_state.generated):
        st.chat_message("user").write(u)
        st.chat_message("assistant").write(b)
            
    #text input field must be rendered after input set
    st.text_input(
        label="You:",
        key="user_input",
        on_change=_on_enter,
        placeholder="Type your message and press Enter…",
    )

    st.button("Enter", on_click=_on_enter)

st.write("To logout please refresh 🔄 the webpage. Thank you for trying GAIA 🤖!")
