__author__ = 'tanel'

import argparse
from ws4py.client.threadedclient import WebSocketClient
import time
import threading
import sys
import urllib
import Queue
import json

class MyClient(WebSocketClient):

    def __init__(self, filename, url, protocols=None, extensions=None, heartbeat_freq=None, byterate=32000):
        super(MyClient, self).__init__(url, protocols, extensions, heartbeat_freq)
        self.final_hyps = []
        self.fn = filename
        self.byterate = byterate
        self.final_hyp_queue = Queue.Queue()

    def opened(self):
        #print "Socket opened!"
        def send_data_to_ws():
            f = open(self.fn, "rb")
            do_wait = False
            for block in iter(lambda: f.read(self.byterate), ""):
                if do_wait:
                    time.sleep(1)
                self.send(block, binary=True)
                do_wait = True
            self.send("EOS")

        t = threading.Thread(target=send_data_to_ws)
        t.start()


    def received_message(self, m):
        response = json.loads(str(m))
        #print >> sys.stderr, "RESPONSE:", response
        #print >> sys.stderr, "JSON was:", m
        if response['status'] == 0:
            if response['result']['final']:
                trans = response['result']['hypotheses'][0]['transcript']
                #print >> sys.stderr, trans,
                self.final_hyps.append(trans)


    def get_full_hyp(self, timeout=60):
        return self.final_hyp_queue.get(timeout)

    def closed(self, code, reason=None):
        #print "Websocket closed() called"
        #print >> sys.stderr
        self.final_hyp_queue.put(" ".join(self.final_hyps))


def main():

    parser = argparse.ArgumentParser(description='Command line client for kaldigstserver')
    parser.add_argument('-u', '--uri', default="ws://localhost:8888/client/ws/speech", dest="uri", help="Server websocket URI")
    parser.add_argument('-r', '--rate', default=32000, dest="rate", type=int, help="Rate in bytes/sec at which audio should be sent to the server. NB! For raw 16-bit audio it must be 2*samplerate!")
    parser.add_argument('audiofile', help="Audio file to be sent to the server")
    args = parser.parse_args()

    content_type = ''
    if args.audiofile.endswith(".raw"):
        content_type = "audio/x-raw, layout=(string)interleaved, rate=(int)%d, format=(string)S16LE, channels=(int)1" %(args.rate/2)


    ws = MyClient(args.audiofile, args.uri + '?%s' % (urllib.urlencode([("content-type", content_type)])))
    ws.connect()
    result = ws.get_full_hyp()
    print result.encode('utf-8')

if __name__ == "__main__":
    main()

