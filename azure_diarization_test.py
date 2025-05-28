import azure.cognitiveservices.speech as speechsdk
import os
import time

speech_key = "8sTDtUGB6YcaENbMygEAbBx8KFb9JWJJqH21QvkeYT979zp6gBxUJQQJ99BEACYeBjFXJ3w3AAAYACOGdl81"
service_region = "eastus"
audio_filename = os.path.expanduser("~/Desktop/samples_csharp_sharedcontent_console_whatstheweatherlike.wav")

speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
audio_config = speechsdk.audio.AudioConfig(filename=audio_filename)

transcriber = speechsdk.transcription.ConversationTranscriber(speech_config=speech_config, audio_config=audio_config)

def transcribed(evt):
    print(f"Transcribed: {evt.result.text}")
    if evt.result.speaker_id:
        print(f"  Speaker: {evt.result.speaker_id}")

def session_stopped(evt):
    print("Transcripción finalizada.")
    global done
    done = True

transcriber.transcribed.connect(transcribed)
transcriber.session_stopped.connect(session_stopped)

print("Reconociendo y diarizando...")
done = False
transcriber.start_transcribing_async().get()

while not done:
    time.sleep(0.5)

transcriber.stop_transcribing_async().get() 