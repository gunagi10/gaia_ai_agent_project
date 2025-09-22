from datetime import datetime
import pytz
import streamlit as st
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
import uuid

import os
from agent_tools import (
    verify_user_tool,
    search_tool,
    query_personal_tax_info_tool,
    create_booking_tool,
    update_booking_tool
)

VANCOUVER = pytz.timezone("America/Vancouver")
today_str = datetime.now(VANCOUVER).strftime("%A, %d %B %Y")

# ─── 1) MODEL SETUP ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv() 

OPENAI_KEY = os.environ["OPENAI_API_KEY"]

model = ChatOpenAI(
    model_name="gpt-4o-mini",
    temperature=0,
    openai_api_key=OPENAI_KEY
)

# ─── 2) TOOLS only ────────────────────────────────────────────────────

tools = [
    search_tool,
    query_personal_tax_info_tool,
    verify_user_tool,
    create_booking_tool,
    update_booking_tool
]

# generate once per user session
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# Saves user config, connected to the generated thread id above
my_config = {
    "configurable": {
        "thread_id": st.session_state.thread_id
    }
}
#######################################

system_prompt = f"""
- You are GAIA (Gian's AI Agent), a funny, cheerful, helpful specialized AI Agent that will answer user's question to the best of your ability. 
- **Before** you answer anything or call any other tool, you **must** call `verify_user` tool. 
- Tell users you need their correct full name and id before being able to help them.
- Once user is verified, refer to their first name often to show your friendliness.

Constraints:
- Use only standard ASCII characters (A–Z, a–z, 0–9, basic punctuation). Do not use fancy Unicode fonts or stylistic letters.
- If you use a tool and its output contains URLs or links, you must always include those URLs in your answer, formatted as clickable markdown links. Never omit or paraphrase away the URLs. If summarizing, always cite the original links.
- If user asks information about Canada's attractions, and anything related to Canada's tax (regulations, tax consulting offices, accounting firms, etc.), answer through 'search_tool'. 
- Other than Canada's attraction and taxes, politely refuse to answer user's inquiry.
- Today's date is {today_str}
- If the user says “list my bookings” or “what are my upcoming meetings?” or anything like that, call the update_booking tool with *no* dates—just:
```python
update_booking()
"""
system_message = SystemMessage(content=system_prompt)


# ─── 3) CHAT SESSION WRAPPER ─────────────────────────────────────────────────────
# Creates chat session class - core of ai brain
# basically accepts user input, sends to langgraph agent, streams back the ai response, and stores the full conv
class ChatSession:

    # init method runs when class is created. inputs (saves) my agent, and system message
    def __init__(self, agent_executor, system_message):
        self.agent = agent_executor
        self.history = [system_message]

    # Send method. The input is user text (latest message from user)
    def send(self, user_text: str) -> str:
        # 1) record user (Appends the new user message to user.history as human message)
        self.history.append(HumanMessage(content=user_text))
        reply = ""
        # 2) stream the agent, passing in your stored config
        for step in self.agent.stream(
            {"messages": self.history},
            config=my_config,
            stream_mode="values"
        ):
            # In each step: Update reply to most recent messgae from the ai -1.content
            reply = step["messages"][-1].content
        # 3) Appends ai reply to self history as an AImessage.
        self.history.append(AIMessage(content=reply))
        # 4) returns reply as plain string.
        return reply
