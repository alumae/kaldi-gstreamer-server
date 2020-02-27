__author__ = 'tanel'

import argparse
#from ws4py.client.threadedclient import WebSocketClient
import time
import threading
import sys
import urllib
import queue
import json
import time
import os
from tornado.ioloop import IOLoop
from tornado import gen
from tornado.websocket import websocket_connect
from concurrent.futures import ThreadPoolExecutor
from tornado.concurrent import run_on_executor


def rate_limited(maxPerSecond):
    min_interval = 1.0 / float(maxPerSecond)
    def decorate(func):
        last_time_called = [0.0]
        def rate_limited_function(*args,**kargs):
            elapsed = time.clock() - last_time_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                yield gen.sleep(left_to_wait)
            ret = func(*args,**kargs)
            last_time_called[0] = time.clock()
            return ret
        return rate_limited_function
    return decorate

executor = ThreadPoolExecutor(max_workers=5)

class MyClient():

    def __init__(self, audiofile, url, byterate=32000,
                 save_adaptation_state_filename=None, send_adaptation_state_filename=None):
        self.url = url
        self.final_hyps = []
        self.audiofile = audiofile
        self.byterate = byterate
        self.final_hyp_queue = queue.Queue()
        self.save_adaptation_state_filename = save_adaptation_state_filename
        self.send_adaptation_state_filename = send_adaptation_state_filename
        self.ioloop = IOLoop.instance()
        self.run()
        self.ioloop.start()

    
    @gen.coroutine
    def run(self):
        self.ws = yield websocket_connect(self.url, on_message_callback=self.received_message)
        if self.send_adaptation_state_filename is not None:
            print("Sending adaptation state from " + self.send_adaptation_state_filename)
            try:
                adaptation_state_props = json.load(open(self.send_adaptation_state_filename, "r"))
                self.ws.write_message(json.dumps(dict(adaptation_state=adaptation_state_props)))
            except:
                e = sys.exc_info()[0]
                print("Failed to send adaptation state: " + e)
        with self.audiofile as audiostream:
            while True:
                block = yield from self.ioloop.run_in_executor(executor, audiostream.read, int(self.byterate/4))
                if block == b"":
                    break
                yield self.send_data(block)
        self.ws.write_message("EOS")

    
    @gen.coroutine
    @rate_limited(4)
    def send_data(self, data):
        self.ws.write_message(data, binary=True)


    def received_message(self, m):
        if m is None:
            #print("Websocket closed() called")
            self.final_hyp_queue.put(" ".join(self.final_hyps))
            self.ioloop.stop()

            return

        #print("Received message ...")
        #print(str(m) + "\n")
        response = json.loads(str(m))
        
        if response['status'] == 0:
            #print(response)
            if 'result' in response:
                trans = response['result']['hypotheses'][0]['transcript']
                if response['result']['final']:
                    self.final_hyps.append(trans)
                    print(trans.replace("\n", "\\n"), end="\n")
                else:
                    print_trans = trans.replace("\n", "\\n")
                    if len(print_trans) > 80:
                        print_trans = "... %s" % print_trans[-76:]
                    print(print_trans, end="\r")
            if 'adaptation_state' in response:
                if self.save_adaptation_state_filename:
                    print("Saving adaptation state to " + self.save_adaptation_state_filename)
                    with open(self.save_adaptation_state_filename, "w") as f:
                        f.write(json.dumps(response['adaptation_state']))
        else:
            print("Received error from server (status %d)" % response['status'])
            if 'message' in response:
                print("Error message:" + response['message'])


    def get_full_hyp(self, timeout=60):
        return self.final_hyp_queue.get(timeout)

    # def closed(self, code, reason=None):
    #     print("Websocket closed() called")
    #     self.final_hyp_queue.put(" ".join(self.final_hyps))


def main():

    parser = argparse.ArgumentParser(description='Command line client for kaldigstserver')
    parser.add_argument('-u', '--uri', default="ws://localhost:8888/client/ws/speech", dest="uri", help="Server websocket URI")
    parser.add_argument('-r', '--rate', default=32000, dest="rate", type=int, help="Rate in bytes/sec at which audio should be sent to the server. NB! For raw 16-bit audio it must be 2*samplerate!")
    parser.add_argument('--save-adaptation-state', help="Save adaptation state to file")
    parser.add_argument('--send-adaptation-state', help="Send adaptation state from file")
    parser.add_argument('--content-type', default='', help="Use the specified content type (empty by default, for raw files the default is  audio/x-raw, layout=(string)interleaved, rate=(int)<rate>, format=(string)S16LE, channels=(int)1")
    parser.add_argument('audiofile', help="Audio file to be sent to the server", type=argparse.FileType('rb'), default=sys.stdin)
    args = parser.parse_args()

    content_type = args.content_type
    if content_type == '' and args.audiofile.name.endswith(".raw"):
        content_type = "audio/x-raw, layout=(string)interleaved, rate=(int)%d, format=(string)S16LE, channels=(int)1" %(args.rate/2)



    ws = MyClient(args.audiofile, args.uri + '?%s' % (urllib.parse.urlencode([("content-type", content_type)])), byterate=args.rate,
                  save_adaptation_state_filename=args.save_adaptation_state, send_adaptation_state_filename=args.send_adaptation_state)
    
    result = ws.get_full_hyp()
    print(result)
    

if __name__ == "__main__":
    main()

