# -*- encoding: UTF-8 -*-
import threading 
import time
import os
import pyaudio
import wave


class Recorder(threading.Thread): 
    def __init__(self,rate): 
        threading.Thread.__init__(self) 
        self.p = pyaudio.PyAudio()
        self.isrunning = False
        self.buffer = []
        self.chunk = rate/8
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.recording = False
        self.stream = None
        self.state = 0

      
        
    def run(self): 
        self.state = 1
        self.isrunning = True
        self.stream = self.p.open(format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk)
        
        while self.isrunning:          
            if self.recording:
                data = self.stream.read(self.chunk)
                self.buffer.append(data)
                #print "Longueur du buffer : ", len(self.bufferc)

  
    def stop(self):
        self.isrunning = False 
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()

    def stop_recoding(self):
        self.recording = False
        #self.buffer = []

    def start_recording(self):
        self.recording = True 


        
