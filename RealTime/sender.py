# -*- encoding: UTF-8 -*-
import time
import threading
import wave

class Sender(threading.Thread): 
    def __init__(self,ws,recorder,condition):
    	threading.Thread.__init__(self) 
    	self.ws = ws
    	self.recorder = recorder
    	self.condition = condition
    	self.isrunning = False
    	self.isSending = False
    	self.num_seg = 0

      
        
    def run(self):


        print "* Sender initialised !"
        self.isrunning = True

        while self.isrunning:
            while self.isrunning and len(self.recorder.buffer) < 2:
                time.sleep(0.001)

            if self.condition() and self.isSending:
                k = len(self.recorder.buffer) - 1
                indice_last_condition = k
                while self.isrunning and self.condition() and self.isSending:
                    if k < len(self.recorder.buffer):
                        self.ws.send_data(b''.join(self.recorder.buffer[k]))    
                        k+=1 
                print "Boucle finie !"
                wf = wave.open("data/wav_"+str(self.num_seg)+".wav", 'wb')
                wf.setnchannels(self.recorder.channels)
                wf.setsampwidth(self.recorder.p.get_sample_size(self.recorder.format))
                wf.setframerate(self.recorder.rate)
                wf.writeframes(b''.join(self.recorder.buffer[indice_last_condition:k]))
                wf.close()
                print "* Wav "+"data/wav_"+str(self.num_seg)+".wav saved !"
                self.num_seg+=1
                self.ws.set_nextSegment(self.num_seg)


            
  
    def stop(self):
        self.isrunning = False

    def stop_sending(self) :
    	self.isSending = False

    def start_sending(self):
    	self.isSending = True

