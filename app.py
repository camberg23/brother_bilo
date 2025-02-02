import logging
import logging.handlers
import queue
import threading
import time
import urllib.request
import os
from collections import deque
from pathlib import Path
from typing import List

import av
import numpy as np
import pydub
import streamlit as st
from twilio.rest import Client

from streamlit_webrtc import WebRtcMode, webrtc_streamer

HERE = Path(__file__).parent
logger = logging.getLogger(__name__)

# This code is based on https://github.com/streamlit/demo-self-driving/blob/230245391f2dda0cb464008195a470751c01770b/streamlit_app.py#L48  # noqa: E501
def download_file(url, download_to: Path, expected_size=None):
    # Don't download the file twice.
    # (If possible, verify the download using the file length.)
    if download_to.exists():
        if expected_size:
            if download_to.stat().st_size == expected_size:
                return
        else:
            st.info(f"{url} is already downloaded.")
            if not st.button("Download again?"):
                return

    download_to.parent.mkdir(parents=True, exist_ok=True)

    # These are handles to two visual elements to animate.
    weights_warning, progress_bar = None, None
    try:
        weights_warning = st.warning("Downloading %s..." % url)
        progress_bar = st.progress(0)
        with open(download_to, "wb") as output_file:
            with urllib.request.urlopen(url) as response:
                length = int(response.info()["Content-Length"])
                counter = 0.0
                MEGABYTES = 2.0 ** 20.0
                while True:
                    data = response.read(8192)
                    if not data:
                        break
                    counter += len(data)
                    output_file.write(data)

                    # We perform animation by overwriting the elements.
                    weights_warning.warning(
                        "Downloading %s... (%6.2f/%6.2f MB)"
                        % (url, counter / MEGABYTES, length / MEGABYTES)
                    )
                    progress_bar.progress(min(counter / length, 1.0))
    # Finally, we remove these visual elements by calling .empty().
    finally:
        if weights_warning is not None:
            weights_warning.empty()
        if progress_bar is not None:
            progress_bar.empty()


# This code is based on https://github.com/whitphx/streamlit-webrtc/blob/c1fe3c783c9e8042ce0c95d789e833233fd82e74/sample_utils/turn.py
@st.cache_data  # type: ignore
def get_ice_servers():
    """Use Twilio's TURN server because Streamlit Community Cloud has changed
    its infrastructure and WebRTC connection cannot be established without TURN server now.  # noqa: E501
    We considered Open Relay Project (https://www.metered.ca/tools/openrelay/) too,
    but it is not stable and hardly works as some people reported like https://github.com/aiortc/aiortc/issues/832#issuecomment-1482420656  # noqa: E501
    See https://github.com/whitphx/streamlit-webrtc/issues/1213
    """

    # Ref: https://www.twilio.com/docs/stun-turn/api
    try:
        account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    except KeyError:
        logger.warning(
            "Twilio credentials are not set. Fallback to a free STUN server from Google."  # noqa: E501
        )
        return [{"urls": ["stun:stun.l.google.com:19302"]}]

    client = Client(account_sid, auth_token)

    token = client.tokens.create()

    return token.ice_servers

def main():
    st.header("Real Time Speech-to-Text")
    st.markdown(
        """
This demo app is using [DeepSpeech](https://github.com/mozilla/DeepSpeech),
an open speech-to-text engine.

A pre-trained model released with
[v0.9.3](https://github.com/mozilla/DeepSpeech/releases/tag/v0.9.3),
trained on American English is being served.
"""
    )

    # https://github.com/mozilla/DeepSpeech/releases/tag/v0.9.3
    MODEL_URL = "https://github.com/mozilla/DeepSpeech/releases/download/v0.9.3/deepspeech-0.9.3-models.pbmm"  # noqa
    LANG_MODEL_URL = "https://github.com/mozilla/DeepSpeech/releases/download/v0.9.3/deepspeech-0.9.3-models.scorer"  # noqa
    MODEL_LOCAL_PATH = HERE / "models/deepspeech-0.9.3-models.pbmm"
    LANG_MODEL_LOCAL_PATH = HERE / "models/deepspeech-0.9.3-models.scorer"

    download_file(MODEL_URL, MODEL_LOCAL_PATH, expected_size=188915987)
    download_file(LANG_MODEL_URL, LANG_MODEL_LOCAL_PATH, expected_size=953363776)

    lm_alpha = 0.931289039105002
    lm_beta = 1.1834137581510284
    beam = 100

    sound_only_page = "Sound only (sendonly)"
    # with_video_page = "With video (sendrecv)"
    # app_mode = st.selectbox("Choose the app mode", [sound_only_page, with_video_page])
    app_mode = sound_only_page

    if app_mode == sound_only_page:
        app_sst()
            # str(MODEL_LOCAL_PATH), str(LANG_MODEL_LOCAL_PATH), lm_alpha, lm_beta, beam
        # )


from deepgram import Deepgram
import numpy as np
import pydub
import asyncio

# Initialize Deepgram SDK
DEEPGRAM_API_KEY = st.secrets['DEEPGRAM']
deepgram = Deepgram(DEEPGRAM_API_KEY)

# async def transcribe_stream(audio_stream, text_output):
#     # Create a websocket connection to Deepgram
#     deepgram_live = await deepgram.transcription.live({'punctuate': True, 'language': 'en-US'})

#     # Process and send audio stream to Deepgram
#     for audio_frame in audio_stream:
#         sound = pydub.AudioSegment(
#             data=audio_frame.to_ndarray().tobytes(),
#             sample_width=audio_frame.format.bytes,
#             frame_rate=audio_frame.sample_rate,
#             channels=len(audio_frame.layout.channels),
#         )
#         buffer = np.array(sound.get_array_of_samples())
#         deepgram_live.send(buffer)

#     # Close the connection
#     await deepgram_live.finish()

# async def transcribe_stream(audio_stream, text_output):
#     try:
#         deepgram_live = await deepgram.transcription.live({'punctuate': True, 'language': 'en-US'})
#         st.write("WebSocket Connection Status:", deepgram_live)
#         if not deepgram_live:
#             print("Failed to establish WebSocket connection.")
#             return
#     except Exception as e:
#         print(f"Error establishing WebSocket connection: {e}")
#         return

#     for audio_frame in audio_stream:
#         frame_bytes = audio_frame.to_ndarray().tobytes()
#         st.write(f"Frame size: {len(frame_bytes)}, type: {type(frame_bytes)}")

#         try:
#             if frame_bytes:
#                 await deepgram_live.send(frame_bytes)
#             else:
#                 st.write("frame_bytes is None or empty, skipping.")
#         except Exception as e:
#             st.write(f"Error sending data: {e}")

#     await deepgram_live.finish()

async def transcribe_stream(audio_stream, text_output):
    deepgram_live = await deepgram.transcription.live({
        'smart_format': True,
        'interim_results': False,
        'language': 'en-US',
        'model': 'nova-2',
    })

    deepgram_live.register_handler(deepgram_live.event.TRANSCRIPT_RECEIVED, lambda result: text_output.write(result['channel']['alternatives'][0]['transcript']))
    deepgram_live.register_handler(deepgram_live.event.CLOSE, lambda _: text_output.write('Connection closed.'))
    deepgram_live.register_handler(deepgram_live.event.ERROR, lambda error: text_output.write(f'Error: {error}'))

    for audio_frame in audio_stream:
        frame_bytes = audio_frame.to_ndarray().tobytes()
        await deepgram_live.send(frame_bytes)

    await deepgram_live.finish()

def app_sst():
    webrtc_ctx = webrtc_streamer(
        key="speech-to-text",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=1024,
        rtc_configuration={"iceServers": get_ice_servers()},
        media_stream_constraints={"video": False, "audio": True},
    )

    text_output = st.empty()

    if webrtc_ctx.audio_receiver:
        while True:
            try:
                audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
                if audio_frames:
                    asyncio.run(transcribe_stream(audio_frames, text_output))
            except queue.Empty:
                st.write("Waiting for audio frames...")
                time.sleep(0.1)

# def app_sst():
#     webrtc_ctx = webrtc_streamer(
#         key="speech-to-text",
#         mode=WebRtcMode.SENDONLY,
#         audio_receiver_size=1024,
#         rtc_configuration={"iceServers": get_ice_servers()},
#         media_stream_constraints={"video": False, "audio": True},
#     )

#     text_output = st.empty()

#     if webrtc_ctx.audio_receiver:
#         audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
#         asyncio.run(transcribe_stream(audio_frames, text_output))


# def app_sst(model_path: str, lm_path: str, lm_alpha: float, lm_beta: float, beam: int):
#     webrtc_ctx = webrtc_streamer(
#         key="speech-to-text",
#         mode=WebRtcMode.SENDONLY,
#         audio_receiver_size=1024,
#         rtc_configuration={"iceServers": get_ice_servers()},
#         media_stream_constraints={"video": False, "audio": True},
#     )

#     status_indicator = st.empty()

#     if not webrtc_ctx.state.playing:
#         return

#     status_indicator.write("Loading...")
#     text_output = st.empty()
#     stream = None

#     while True:
#         if webrtc_ctx.audio_receiver:
#             if stream is None:
#                 from deepspeech import Model

#                 model = Model(model_path)
#                 model.enableExternalScorer(lm_path)
#                 model.setScorerAlphaBeta(lm_alpha, lm_beta)
#                 model.setBeamWidth(beam)

#                 stream = model.createStream()

#                 status_indicator.write("Model loaded.")

#             sound_chunk = pydub.AudioSegment.empty()
#             try:
#                 audio_frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
#             except queue.Empty:
#                 time.sleep(0.1)
#                 status_indicator.write("No frame arrived.")
#                 continue

#             status_indicator.write("Running. Say something!")

#             for audio_frame in audio_frames:
#                 sound = pydub.AudioSegment(
#                     data=audio_frame.to_ndarray().tobytes(),
#                     sample_width=audio_frame.format.bytes,
#                     frame_rate=audio_frame.sample_rate,
#                     channels=len(audio_frame.layout.channels),
#                 )
#                 sound_chunk += sound

#             if len(sound_chunk) > 0:
#                 sound_chunk = sound_chunk.set_channels(1).set_frame_rate(
#                     model.sampleRate()
#                 )
#                 buffer = np.array(sound_chunk.get_array_of_samples())
#                 stream.feedAudioContent(buffer)
#                 text = stream.intermediateDecode()
#                 text_output.markdown(f"**Text:** {text}")
#         else:
#             status_indicator.write("AudioReciver is not set. Abort.")
#             break

if __name__ == "__main__":
    import os

    DEBUG = os.environ.get("DEBUG", "false").lower() not in ["false", "no", "0"]

    logging.basicConfig(
        format="[%(asctime)s] %(levelname)7s from %(name)s in %(pathname)s:%(lineno)d: "
        "%(message)s",
        force=True,
    )

    logger.setLevel(level=logging.DEBUG if DEBUG else logging.INFO)

    st_webrtc_logger = logging.getLogger("streamlit_webrtc")
    st_webrtc_logger.setLevel(logging.DEBUG)

    fsevents_logger = logging.getLogger("fsevents")
    fsevents_logger.setLevel(logging.WARNING)

    main()
