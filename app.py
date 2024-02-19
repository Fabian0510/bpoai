import streamlit as st
import websockets
import asyncio
import base64
import json
import pyaudio
import os
from pathlib import Path
import requests as r
import pandas as pd

# Session state
if 'text' not in st.session_state:
	st.session_state['text'] = 'Listening...'
	st.session_state['run'] = False

# Audio parameters 
st.sidebar.header('Audio Parameters')

FRAMES_PER_BUFFER = int(st.sidebar.text_input('Frames per buffer', 3200))
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = int(st.sidebar.text_input('Rate', 16000))
p = pyaudio.PyAudio()

# Open an audio stream with above parameter settings
stream = p.open(
   format=FORMAT,
   channels=CHANNELS,
   rate=RATE,
   input=True,
   frames_per_buffer=FRAMES_PER_BUFFER
)

# Start/stop audio transmission
def start_listening():
	st.session_state['run'] = True

def download_transcription():
	read_txt = open('transcription.txt', 'r')
	st.download_button(
		label="Download transcription",
		data=read_txt,
		file_name='transcription_output.txt',
		mime='text/plain')

def stop_listening():
	st.session_state['run'] = False

def send_to_llm(llm_text,model):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": "Please parse out the subjects and the sentiment associated with them (from 0 to 10, bad to good) in the format \"{subject:sentiment}\", discussed in the following sentence; only reply in JSON: " + llm_text,
        "stream": False
    }
    headers = {'Content-Type': 'application/json'}

    response = r.post(url, data=json.dumps(payload), headers=headers)

    if response.status_code == 200:
        response_data = response.json()
        print(response_data['response'])
        return response_data['response']
    else:
        print(f"Request failed with status code {response.status_code}")
        return None

# Web user interface
st.title('BPO.AI')


col1, col2 = st.columns(2)

col1.button('Start', on_click=start_listening)
col2.button('Stop', on_click=stop_listening)

model_radio = st.radio('Model', ['mistral', 'llama2'])
col3, col4 = st.columns(2)
	
# cont2 = st.container()
with col3:
	st.header('📱Transcription')


# cont1 = st.container()
with col4:
	st.header('🤖LLM')
# Send audio (Input) / Receive transcription (Output)
async def send_receive():
	URL = f"wss://api.assemblyai.com/v2/realtime/ws?sample_rate={RATE}"

	print(f'Connecting websocket to url ${URL}')

	async with websockets.connect(
		URL,
		extra_headers=(("Authorization", st.secrets['api_key']),),
		ping_interval=5,
		ping_timeout=20
	) as _ws:

		r = await asyncio.sleep(0.1)
		print("Receiving messages ...")

		session_begins = await _ws.recv()
		print(session_begins)
		print("Sending messages ...")


		async def send():
			while st.session_state['run']:
				try:
					data = stream.read(FRAMES_PER_BUFFER)
					data = base64.b64encode(data).decode("utf-8")
					json_data = json.dumps({"audio_data":str(data)})
					r = await _ws.send(json_data)

				except websockets.exceptions.ConnectionClosedError as e:
					print(e)
					assert e.code == 4008
					break

				except Exception as e:
					print(e)
					assert False, "Not a websocket 4008 error"

				r = await asyncio.sleep(0.01)


		async def receive():
			while st.session_state['run']:
				try:
					result_str = await _ws.recv()
					result = json.loads(result_str)['text']

					if json.loads(result_str)['message_type']=='FinalTranscript':
						print(result)
						st.session_state['text'] = result
						col3.write(st.session_state['text'])
						col4.json(send_to_llm(result,model_radio))

						transcription_txt = open('transcription.txt', 'a')
						transcription_txt.write(st.session_state['text'])
						transcription_txt.write(' ')
						transcription_txt.close()


				except websockets.exceptions.ConnectionClosedError as e:
					print(e)
					assert e.code == 4008
					break

				except Exception as e:
					print(e)
					assert False, "Not a websocket 4008 error"
			
		send_result, receive_result = await asyncio.gather(send(), receive())


asyncio.run(send_receive())

if Path('transcription.txt').is_file():
	st.markdown('### Download')
	download_transcription()
	os.remove('transcription.txt')

# References (Code modified and adapted from the following)
# 1. https://github.com/misraturp/Real-time-transcription-from-microphone
# 2. https://medium.com/towards-data-science/real-time-speech-recognition-python-assemblyai-13d35eeed226