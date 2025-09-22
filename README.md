# AI Agent Chat Application with Google Calendar integration and ability to internet search and read Database (GAIA - Gian's AI Agent)

This project is my first AI Agent project that I created with very limited python knowledge and no technical background. I started with only https://python.langchain.com/docs/introduction/ and ChatGPT as the main resources (This was about April 2025 so ChatGPT wasn't that great at coding as there were only ChatGPT 4). Somewhere along the way I read various documentations, Youtube videos, StackOverflow, Reddit forums to obtain the information needed to add features to the app, one step at a time. In the end I even learned and used docker and published the app to the cloud with DigitalOcean so that it's accessible from the internet. I learned so much during the journey to create this web app, and that is when I realize that I want to learn more of coding and AI agent itself. I know the app is not perfect, but I am proud of myself that I sucessfully added all the functions and changes that I did want to add into it.

I call this project GAIA, it is an AI-powered chat application that acts as an assistant for the owner (users are customers). I give it tools, but GAIA will choose which tools to use by itself depending on the user's queries.

The idea stems from a personal assistant. If you are a busy tax consultant, perhaps you could not always be available to pick up your customer's calls and requests. So, with GAIA (Gian's AI Agent), first you MUST present correct full name and ID that acts as a sign in in the chat, then you will have to GAIA's 3 functions:
1. you can talk to it to ask about your information that's stored in the company database (in here it's MongoDB), 
2. ask queries that it can answer by internet search (Tavily search), 
3. and you can talk to it to directly book meeting that will appear on the program's owner's calendar (in this example it's my google calendar).

I made the webapp to have these additional features because I thought of them (this was my first AI Agent project, so I was trying various things):
1. It has voice mode tab; you can record your voice, it will be transcribed and sent to GAIA, then GAIA will provide you with the answer also verbally (this takes much more tokens though so be careful when testing this one).
2. I added admin tab. This allows user to delete, edit, or add existing accounts in the database.

## Project Structure

### Core Application Files
- `app.py` - Main Streamlit application file that runs the web interface
- `agent_core.py` - Core AI agent functionality and logic
- `agent_tools.py` - Collection of tools and utilities used by the AI agent
- `whisper.py` - Speech-to-text functionality implementation
- `calendar_connect.py` - Google Calendar integration and authentication (The first time you run the program, you will need to run this separately so that it can have access to your google calendar)
- `import_tax_records.py` - Utility for importing and processing tax records (You will need this for the first time to have access to dummy files that you can use for demo)
- `tax_records.csv` - Sample tax records data file for demo

### Configuration Files
- `requirements.txt` - Python package dependencies

## Required Setup

### Missing Files (Need to be obtained separately)
1. `credentials.json`
   - Required for Google Calendar integration
   - Contains OAuth 2.0 client credentials
   - How to obtain:
     1. Go to Google Cloud Console
     2. Create a new project or select existing one
     3. Enable Google Calendar API
     4. Create OAuth 2.0 credentials
     5. Download the credentials file and rename it to `credentials.json`

2. `.env` file
   - Required for environment variables and API keys
   - Should contain:
   ```bash
   OPENAI_API_KEY=sk-pr...
   TAVILY_API_KEY=tvly-dev-NU...
   LANGSMITH_API_KEY=lsv... # this one is optional if you don't want to monitor through langsmith website
   MONGO_URI=mongodb+srv://admin:...
   MONGO_DB = ...
   MONGO_COLL=...
   ```
### Need to be prepared
1. MongoDB Atlas; get `MONGO_URI`, `MONGO_DB`, `MONGO_COLL`. We need this to load `tax_records.csv` into a MongoDB collection using `import_tax_records.py`
   - Create a free cluster
      1. Go to MongoDB Atlas → Sign in / Sign up
      2. Create a Free (M0) cluster
      3. Choose any cloud + region (defaults are fine)

   - Create a database user
      1. In Atlas, open Database Access → Add New Database User
      2. Set a username & password
      3. Role → Read and write to any database
      4. Save the credentials (you’ll need them in the URI)

   - Allow network access
      1. Go to Network Access → Add IP Address
      2. Either click Allow Access from Anywhere (0.0.0.0/0) or add your current IP

   - Get the connection string
      1. Databases → Connect → Drivers
      2. Copy the URI (example):
      3. mongodb+srv://<user>:<password>@cluster0.xxyyy.mongodb.net/?retryWrites=true&w=majority
      4. Replace <user> and <password> with the ones you created.

   - Choose DB and collection names
      1. Pick any names (e.g. ai_agent_tax and tax_records).
      2. No need to pre-create them; Mongo will create them on first insert.

   - Add to .env, example below:
      ```bash
      MONGO_URI=mongodb+srv://user:pass@cluster0.xxyyy.mongodb.net/?retryWrites=true&w=majority
      MONGO_DB=ai_agent_tax
      MONGO_COLL=tax_records
      ```

2. LangSmith (FREE - if you choose to use LangChain's tracing and observability platform). 
   Create an account and get the API key. This webpage contains the guide -> https://docs.langchain.com/langsmith/create-account-api-key

3. Tavily API key (FREE - So your AI Agent can access internet search)
   Create an account and get the API key. -> https://docs.tavily.com/documentation/quickstart

4. OpenAI API Key (PAID - this is your AI Agent's brain). 
   After you create an account at platform.openai.com, add some funds to your account ($5 is much more than enough for testing and demo purposes), you can request an API key, put it in .env and use it.

### Complete Steps from installation until app is running:
1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Place the required `credentials.json` and `.env` files in the project root directory

4. You should ensure to already have a MongoDB collection () and the google cloud project is setup properly

5. Run below code to populate your MongoDB table so you can inquire information regarding the content of logged in user.
   ```bash
   python import_tax_records.py
   ```

6. Run below code to allow access to your google calendar, so that when someone wants to book a meeting, your google calendar will be updated. Token.json will appear after you run the code and login successfully.
   ```bash
   python calendar_connect.py
   ```

7. Run the application:
   ```bash
   streamlit run app.py
   ```

8. Now you can use the webapp. Here are some guide to use it:
- You have navigation tab; 2 Client and 2 Admin facing. To use these tabs use these credentials (username: admin; password: administrator -- You can change them within app.py, code line 90 if you want)
- Be sure to check admin-manage records to see the user's credentials so you can talk to GAIA in both the Client tabs.
- For example type: "Dwight Schrute 112345" and enter, and GAIA will now talk to you.
- Try to ask for your tax information, general questions about Canada's tax or attraction (I limit it this way on purpose in system prompt to test it out), and also to book meetings (the coolest part since the updated meeting bookings and it's details will show up in your google calendar).
- You can try and talk to GAIA in the voice chat tab (Just be reminded that this takes much more tokens).
- You may play around with the admin tab to add or manage records (If you want to refresh the records to the original 10 records from tax_records.csv, just run the import_tax_records.py again)

## Notes
- The application will generate a `token.json` file after the first successful Google Calendar authentication
- Make sure to keep all credential files (`.env`, `credentials.json`) secure and never commit them to version control

