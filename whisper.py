from streamlit_mic_recorder import mic_recorder
import streamlit as st
import io
from openai import OpenAI
import dotenv
import os

openai_api_key = os.environ["OPENAI_API_KEY"]

# This code is Streamlit component that records audio from user's microphone, send to OpenAI whisper API for transcription.
# mic recorder is to record from user's mic and return mp3; Bytesio is to wrap raw audio so whisper can read.

# Function to check whether OpenAI client has been initialized in st.session_state
# If not it loads env variable via dotenv and creates OpenAI client using whisper model.
def whisper_stt(openai_api_key=None, start_prompt="Start recording", stop_prompt="Stop recording", just_once=False,
               use_container_width=False, language=None, callback=None, args=(), kwargs=None, key=None):
    if not 'openai_client' in st.session_state:
        dotenv.load_dotenv()
        st.session_state.openai_client = OpenAI(api_key=openai_api_key or os.getenv('OPENAI_API_KEY'))

    # initializing state for transcript tracking; last audio it processed and last transcript output
    # If you pass a key, stores output in session_state[key+ '_output']
    if not '_last_speech_to_text_transcript_id' in st.session_state:
        st.session_state._last_speech_to_text_transcript_id = 0
    if not '_last_speech_to_text_transcript' in st.session_state:
        st.session_state._last_speech_to_text_transcript = None
    if key and not key + '_output' in st.session_state:
        st.session_state[key + '_output'] = None

    # Recording audio with mic_recorder; when its finished user gets audio content (bytes), and id (recording session id)
    audio = mic_recorder(start_prompt=start_prompt, stop_prompt=stop_prompt, just_once=just_once,
                         use_container_width=use_container_width, key=key)
    new_output = False
    if audio is None:
        output = None
    else:
        id = audio['id']
        new_output = (id > st.session_state._last_speech_to_text_transcript_id)
        if new_output:
            output = None
            st.session_state._last_speech_to_text_transcript_id = id
            audio_bio = io.BytesIO(audio['bytes'])
            audio_bio.name = 'audio.mp3'
            success = False
            err = 0
            while not success and err < 3:  # Retry up to 3 times in case of OpenAI server error.
                
                # sending audio to whisper API
                try:
                    transcript = st.session_state.openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_bio,
                        language=language
                    )
                except Exception as e:
                    print(str(e))  # log the exception in the terminal
                    err += 1
                else:
                    success = True
                    output = transcript.text
                    st.session_state._last_speech_to_text_transcript = output
        elif not just_once:
            output = st.session_state._last_speech_to_text_transcript
        else:
            output = None

    #Saving and returning output
    if key:
        st.session_state[key + '_output'] = output
    if new_output and callback:
        callback(*args, **(kwargs or {}))
    return output
