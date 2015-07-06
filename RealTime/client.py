# -*- encoding: UTF-8 -*-

from ws4py.client.threadedclient import WebSocketClient
import time
import threading
import sys
import urllib
import Queue
import json
from gi.repository import GObject
from Tkinter import *


def rate_limited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)
    def decorate(func):
        lastTimeCalled = [0.0]
        def rate_limited_function(*args,**kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait>0:
                time.sleep(leftToWait)
            ret = func(*args,**kargs)
            lastTimeCalled[0] = time.clock()
            return ret
        return rate_limited_function
    return decorate


class MyClient(WebSocketClient):

    def __init__(self,TextArea, url, protocols=None, extensions=None, heartbeat_freq=None, byterate=32000,
                 save_adaptation_state_filename=None, send_adaptation_state_filename=None):
        super(MyClient, self).__init__(url, protocols, extensions, heartbeat_freq)
        self.final_hyps = []
        self.frames = None
        self.byterate = byterate
        self.isSending = True
        self.final_hyp_queue = Queue.Queue()
        self.save_adaptation_state_filename = save_adaptation_state_filename
        self.send_adaptation_state_filename = send_adaptation_state_filename
        self.currSegment = -1
        self.encours = False
        self.segment_sending = 0 
        self.TextArea = TextArea
        self.currSegment = -1
        self.nextSegment = 0
        self.fichier_ref = None
        self.start_currTrans = "1.0"

    @rate_limited(4)
    def send_data(self, data):
        self.send(data, binary=True)

    def opened(self):
        print "Socket opened!"
        def send_data_to_ws():
            if self.send_adaptation_state_filename is not None:
                print >> sys.stderr, "Sending adaptation state from %s" % self.send_adaptation_state_filename
                try:
                    adaptation_state_props = json.load(open(self.send_adaptation_state_filename, "r"))
                    self.send(json.dumps(dict(adaptation_state=adaptation_state_props)))
                except:
                    e = sys.exc_info()[0]
                    print >> sys.stderr, "Failed to send adaptation state: ",  e

            
            while self.isSending:
                if self.currSegment != self.nextSegment:
                    if self.fichier_ref is not None:
                        self.fichier_ref.close()
                        print "* Transcript "+str(self.currSegment)+" saved !"
                    self.fichier_ref = open("data/trans_"+str(self.nextSegment)+'.txt', "a")
                    self.currSegment = self.nextSegment
                            
            self.send("EOS")


        t = threading.Thread(target=send_data_to_ws)
        t.start()


    def received_message(self, m):
        response = json.loads(str(m))
        #print >> sys.stderr, "RESPONSE:", response
        #print >> sys.stderr, "JSON was:", m
        if response['status'] == 0:
            if 'result' in response:
                trans = response['result']['hypotheses'][0]['transcript']
                if response['result']['final']:
                    #print >> sys.stderr, trans,
                    self.final_hyps.append(trans)
                    print_trans = trans.replace("\n", "\\n")
                    print >> sys.stderr, '\r%s' % print_trans
                    self.TextArea.delete(self.start_currTrans,"end")
                    self.TextArea.insert('end',print_trans)
                    self.start_currTrans = self.TextArea.index(INSERT)
                    if self.fichier_ref is not None:
                        self.fichier_ref.write("Hypothese finale : "+print_trans+"\n")

                else:
                    print_trans = trans.replace("\n", "\\n")
                    if len(print_trans) > 80:
                        print_trans = "... %s" % print_trans[-76:]
                    print >> sys.stderr, '\r%s' % print_trans,
                    self.TextArea.insert('end',print_trans)
                    if self.fichier_ref is not None:
                        self.fichier_ref.write("Hypothese intermediaire : "+print_trans)
                        self.fichier_ref.write("\n")
            if 'adaptation_state' in response:
                if self.save_adaptation_state_filename:
                    print >> sys.stderr, "Saving adaptation state to %s" % self.save_adaptation_state_filename
                    with open(self.save_adaptation_state_filename, "w") as f:
                        f.write(json.dumps(response['adaptation_state']))
        else:
            print >> sys.stderr, "Received error from server (status %d)" % response['status']
            if 'message' in response:
                print >> sys.stderr, "Error message:",  response['message']


    def get_full_hyp(self, timeout=60):
        return self.final_hyp_queue.get(timeout)

    def closed(self, code, reason=None):
        print "Websocket closed() called"
        #print >> sys.stderr
        self.final_hyp_queue.put(" ".join(self.final_hyps))

    def start_Sending(self):
        self.isSending = True

    def stop_Sending(self):
        self.isSending = False

    def set_nextSegment(self,numSegment):
        self.nextSegment = numSegment


