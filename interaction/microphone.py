### capture voice commands and respond accordingly
## HOW IT WORKS: 
## DEPENDENCIES:
# OS:
# Python: SpeechRecognition
## CONFIGURATION:
# required: engine (google|pocketsphinx), speaker
# optional: device
## COMMUNICATION:
# INBOUND: 
# OUTBOUND: 
# - notification/speaker RUN: respond to the voice command through the speaker
# - controller/chatbot ASK: ask the chatbot how to respond to the command

import speech_recognition as sr
import pyttsx3
import os
import requests
import calendar
import numpy as np
import deepspeech
from deepspeech import Model
from scipy.io.wavfile import write

from sdk.python.module.interaction import Interaction
from sdk.python.module.helpers.message import Message

import sdk.python.utils.exceptions as exception
import sdk.python.utils.command
import sdk.python.utils.numbers

# listen from voice input through a microphone
class Microphone(Interaction):
    # What to do when initializing
    def on_init(self):
        self.verbose = True
        self.recorder_max_duration = 60
        self.recorder_start_duration = 0.1
        self.recorder_start_threshold = 1
        self.recorder_end_duration = 3
        self.recorder_end_threshold = 0.1
        # module's configuration
        self.config = {}
        self.house = {}
        # request required configuration files
        self.config_schema = 1
        self.add_configuration_listener("house", 1, True)
        self.add_configuration_listener(self.fullname, "+", True)
        print("Setting model dspeech")
        self.model_file_path = 'dspeech/deepspeech-0.9.3-models.tflite'
        self.model = Model(self.model_file_path)

        self.scorer_file_path = 'dspeech/deepspeech-0.9.3-models.scorer'
        self.model.enableExternalScorer(self.scorer_file_path)
        print("Settedd model dspeech")

        self.listen = True
        self.wake_up_word = False

    # What to do when running
    def on_start(self):
        # start the pulseaudio daemon
        print("starting deaemon")
        self.log_info("Starting audio daemon...")
        #self.log_debug(sdk.python.utils.command.run("setup/start_pulseaudio.sh"))
        # start the service
        input_file = "/tmp/audio_self.input.wav"
        listening_message = True
        while True:
            if self.config["engine"] == "deepspeech":
                if self.listen == False: continue
            else :
                if listening_message: self.log_info("Listening for voice commands...")
                # run sox to record a voice sample trimming silence at the beginning and at the end
                device = "-t alsa "+str(self.config["device"]) if self.config["device"] != "" else ""
                command = "sox "+device+" "+input_file+" trim 0 "+str(self.recorder_max_duration)+" silence 1 "+str(self.recorder_start_duration)+" "+str(self.recorder_start_threshold)+"% 1 "+str(self.recorder_end_duration)+" "+str(self.recorder_end_threshold)+"%"
                sdk.python.utils.command.run(command)
                # ensure the sample contains any sound
                max_amplitude = sdk.python.utils.command.run("killall sox 2>&1 2>/dev/null; sox "+input_file+" -n stat 2>&1|grep 'Maximum amplitude'|awk '{print $3}'")
                if not sdk.python.utils.numbers.is_number(max_amplitude) or float(max_amplitude) == 0: 
                    listening_message = False
                    continue

            self.log_info("Captured voice sample, processing...")
            listening_message = True
            # recognize the speech
            request = ""
            if self.config["engine"] == "google":
                # use the speech recognition engine to make google recognizing the file
                recognizer = sr.Recognizer()
                # open the input file
                with sr.AudioFile(input_file) as source:
                    audio = recognizer.record(source)
                try:
                    # perform the speech recognition
                    results = recognizer.recognize_google(audio, show_all=True, language=self.house["language"])
                    # identify the best result
                    if len(results) != 0:
                        best_result = max(results["alternative"], key=lambda alternative: alternative["confidence"])
                        request = best_result["transcript"]
                except sr.UnknownValueError:
                    self.log_warning("Google Speech Recognition could not understand the audio")
                except speech_recognition.RequestError as e:
                    self.log_warning("Could not request results from Google Speech Recognition module; {0}".format(e))
            elif self.config["engine"] == "pocketsphinx":
                # run pocketsphinx to recognize the speech in the audio file
                language = self.house["language"].replace("-","_")
                command = "pocketsphinx_continuous -infile "+input_file+" -hmm /usr/share/pocketsphinx/model/hmm/"+language+"/hub4wsj_sc_8k/ -dict /usr/share/pocketsphinx/model/lm/"+language+"/cmu07a.dic 2>/dev/null"
                output = sdk.python.utils.command.run(command)
                request = output.replace("000000000: ","")
            elif self.config["engine"] == "deepspeech":
                r = sr.Recognizer()
                with sr.Microphone(sample_rate = 16000)  as source:
                    r.adjust_for_ambient_noise(source)
                    print("Listening...")
                    if self.wake_up_word == True:
                        audio = r.listen(source, phrase_time_limit=8)
                        audio16 = np.frombuffer(audio.frame_data, dtype=np.int16)
                        statement = "NONE"
                        try:
                            text = self.model.stt(audio16)
                            print (text)
                            statement = text
                            if not text:
                                self.wake_up_word = False
                            print("user said:{statement}\n")
                        except Exception as e:
                            print(e)
                    else :
                        audio = r.listen(source, phrase_time_limit=2)
                        audio16 = np.frombuffer(audio.frame_data, dtype=np.int16)
                        statement = "NONE"
                        try:
                            text = self.model.stt(audio16)
                            print (text)
                            if not "hello" in text and not "assistant" in text:
                                continue
                            statement = "egeoffrey"
                        except Exception as e:
                            print(e)
                    request = statement
            
            if self.debug:
                # repeat the question
                message = Message(self)
                message.recipient = "notification/"+self.config["speaker"]
                message.command = "RUN"
                message.args = "info"
                message.set_data("I have understood: "+request)
                self.send(message)
            # ask the chatbot what to respond
            message = Message(self)
            message.recipient = "controller/chatbot"
            message.command = "ASK"
            message.set("request", request)
            message.set("accept", ["text"])
            self.send(message)
            self.listen = False
            print (request)
        
    # What to do when shutting down
    def on_stop(self):
        sdk.python.utils.command.run("killall sox 2>&1 2>/dev/null")
        
    # What to do when receiving a request for this module    
    def on_message(self, message):
        print (message.sender)
        print (message.command)
        # handle response from the chatbot
        if message.sender == "controller/chatbot" and message.command == "ASK":
            content = message.get("content")
            message = Message(self)
            message.recipient = "notification/"+self.config["speaker"]
            message.command = "RUN"
            message.args = "info"
            message.set_data(content)
            self.send(message)
        if message.sender == "notification/speaker" and message.command == "ACK_WAKE_UP":
            print("llego ack wake up")
            if self.listen == False :
                self.listen = True
                self.wake_up_word = True
        if message.sender == "notification/speaker" and message.command == "ACK_LISTEN":
            print("llego ack listen")
            if self.listen == False :
                self.listen = True

     # What to do when receiving a new/updated configuration for this module    
    def on_configuration(self, message):
        if message.args == "house" and not message.is_null:
            if not self.is_valid_configuration(["language"], message.get_data()): return False
            self.house = message.get_data()
        # module's configuration
        if message.args == self.fullname and not message.is_null:
            if message.config_schema != self.config_schema: 
                return False
            if not self.is_valid_configuration(["engine", "speaker"], message.get_data()): return False
            self.config = message.get_data()
