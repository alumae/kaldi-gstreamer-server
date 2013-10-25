from ws4py.client.threadedclient import WebSocketClient
import time
import threading
import sys
import urllib
import Queue
import json

class MyClient(WebSocketClient):
    def opened(self):
        fn = "test/data/test.raw"
        if len(sys.argv) > 1:
            fn = sys.argv[1]
        print "Socket opened!"
        def send_data_to_ws():
            for i in range(1):
                f = open(fn, "rb")
                do_wait = False
                for block in iter(lambda: f.read(2*16000), ""):
                    if do_wait:
                        time.sleep(1)
                    ws.send(block, binary=True)
                    do_wait = True
            ws.send("EOS")
        
        t = threading.Thread(target=send_data_to_ws)
        t.start()        

    
    def received_message(self, m):
        print "RESPONSE:", json.loads(str(m))
        print "JSON was:", m
        
    
    def closed(self, code, reason=None):
        print "Websocket closed() called"
        # notify main thread
        queue.put(1)
        

queue = Queue.Queue()

content_type=""

if len(sys.argv) > 1:
    if sys.argv[1].endswith(".raw"):
        content_type="audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1"
        
    
ws = MyClient('ws://localhost:8888/speech?%s' % (urllib.urlencode([("content-type", content_type)])), protocols=['http-only', 'chat'])
ws.connect()
# wait until socket is closed
MINUTE = 2 * 60
queue.get(timeout=MINUTE)



