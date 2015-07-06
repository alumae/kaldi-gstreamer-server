# -*- encoding: UTF-8 -*-
from Tkinter import *
from recorder import *
from client import *
from sender import *
import time
import sys
import argparse
import os


class Interface(Frame):
    
    """Notre fenêtre principale.
    Tous les widgets sont stockés comme attributs de cette fenêtre."""
    
    def __init__(self, fenetre, args, **kwargs):

        Frame.__init__(self, fenetre, width=768, height=576, **kwargs)
        self.pack()

        # Création des frames
        self.frame1 = Frame(self, width=100, height=200, padx=10, pady=10)
        self.frame1.pack(side=RIGHT,fill=Y)

        self.frame2 = Frame(self,  width=400, height=10)
        self.frame2.pack(side=TOP, fill=X)

        self.frame3 = Frame(self, width=400, height=190, padx=10, pady=10)
        self.frame3.pack(side=LEFT,fill=Y)
        
        # Création de nos widgets
        self.bouton_quitter = Button(self.frame1, text="Quitter", command=self.cliquer_quit)
        self.bouton_quitter.pack(fill=X,pady=20)

        self.bouton_stop = Button(self.frame1, text="Stop", command=self.cliquer_stop)
        self.bouton_stop.pack(fill=X)

        bouton_record = Button(self.frame1, text="Record", command=self.cliquer_record)
        bouton_record.pack(fill=X)

        self.message = Label(self.frame2, text="Transcription : OFF")
        self.message.pack(side="left")

        self.TextArea = Text(self.frame3)
        self.ScrollBar = Scrollbar(self.frame3)
        self.ScrollBar.config(command=self.TextArea.yview)
        self.TextArea.config(yscrollcommand=self.ScrollBar.set)
        self.ScrollBar.pack(side=RIGHT, fill=Y)
        self.TextArea.pack(expand=YES, fill=BOTH,side='bottom')        
        self.isactif = False

        # Objets gérant la transcription        
        content_type = "audio/x-raw, layout=(string)interleaved, rate=(int)%d, format=(string)S16LE, channels=(int)1" %(args.rate/2)  
        self.ws = MyClient(self.TextArea, args.uri + '?%s' % (urllib.urlencode([("content-type", content_type)])), byterate=args.rate,
                          save_adaptation_state_filename=args.save_adaptation_state, send_adaptation_state_filename=args.send_adaptation_state)
        self.recorder = Recorder(args.rate)

        self.premierefois = True


        def condition():
            return True


        self.sender = Sender(self.ws,self.recorder,condition) 


    
    def cliquer_record(self):

        if self.isactif == False :
            if self.premierefois:
                self.ws.connect()
                self.recorder.start()
                self.sender.start()
                self.premierefois = False

            self.message["text"] = "Transcirition : ON"
            self.isactif = True


            self.recorder.start_recording()
            self.sender.start_sending()

        else:
            print "Déjà en cours"


    def cliquer_stop(self):

        self.isactif = False
        self.message["text"] = "Transcirition : OFF"

        self.recorder.stop_recoding()
        self.sender.stop_sending()

    def cliquer_quit(self):

        if self.isactif:
            self.ws.send("EOS")
        if self.recorder.isrunning:
            self.recorder.stop_recoding()
            self.recorder.stop()
            self.recorder.join()
        if self.sender.isrunning:
            self.sender.stop_sending()
            self.sender.stop()
            self.sender.join()
        self.quit()
        print "* Leaving"

        
        

        



def main():


    try:
        parser = argparse.ArgumentParser(description='Command line client for kaldigstserver')
        parser.add_argument('-u', '--uri', default="ws://localhost:8888/client/ws/speech", dest="uri", help="Server websocket URI")
        parser.add_argument('-r', '--rate', default=32000, dest="rate", type=int, help="Rate in bytes/sec at which audio should be sent to the server. NB! For raw 16-bit audio it must be 2*samplerate!")
        parser.add_argument('--save-adaptation-state', help="Save adaptation state to file")
        parser.add_argument('--send-adaptation-state', help="Send adaptation state from file")
        args = parser.parse_args()
        fenetre = Tk()
        fenetre.geometry("800x300")
        fenetre.title("ASR")
        interface = Interface(fenetre,args)
        interface.mainloop()

    except KeyboardInterrupt:
        interface.cliquer_quit()
        exit(0)



if __name__ == '__main__':
    main()