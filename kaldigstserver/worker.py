from gevent.hub import sleep

__author__ = 'tanel'


import logging
import time
import thread
import threading
import argparse
import datetime
from subprocess import Popen, PIPE
from gi.repository import GObject, Gst
import yaml
import json
import signal
import redis

from ws4py.client.threadedclient import WebSocketClient

from decoder import DecoderPipeline
import common



logger = logging.getLogger(__name__)

_redis = None
_redis_namespace = "speech_dev"

CHUNK_TIMEOUT = 10
TIMEOUT_DECODER = 5
EXPIRE_RESULTS = 10
CONNECT_TIMEOUT = 5

class ServerWebsocket(WebSocketClient):

    STATE_CREATED = 0
    STATE_CONNECTED = 1
    STATE_INITIALIZED = 2
    STATE_PROCESSING = 3
    STATE_EOS_RECEIVED = 7
    STATE_CANCELLING = 8
    STATE_FINISHED = 100

    def __init__(self, uri,  decoder_pipeline, post_processor):
        self.uri = uri
        self.decoder_pipeline = decoder_pipeline
        self.post_processor = post_processor
        WebSocketClient.__init__(self, url=uri)
        self.pipeline_initialized = False
        self.partial_transcript = ""
        self.decoder_pipeline.set_word_handler(self._on_word)
        self.decoder_pipeline.set_eos_handler(self._on_eos)
        self.state = self.__class__.STATE_CREATED
        self.last_decoder_message = time.time()

    def opened(self):
        logging.info("Opened websocket connection to server")
        self.state = self.__class__.STATE_CONNECTED

    def guard_timeout(self):
        while self.state != self.__class__.STATE_FINISHED:
            if time.time() - self.last_decoder_message > TIMEOUT_DECODER:
                logger.warning("More than %d seconds from last decoder activity, cancelling" % TIMEOUT_DECODER)
                self.state = self.__class__.STATE_CANCELLING
                self.decoder_pipeline.cancel()
                event = dict(status=common.STATUS_NO_SPEECH)
                self.send(json.dumps(event))
                #self.close()
            logger.info("Waiting for decoder end")
            time.sleep(1)


    def received_message(self, m):
        logging.info("Got message from server of type " + str(type(m)))
        if self.state == self.__class__.STATE_CONNECTED:
            props = json.loads(str(m))
            content_type = props['content_type']
            request_id = props['id']
            self.decoder_pipeline.init_request(request_id, content_type)
            self.last_decoder_message = time.time()
            thread.start_new_thread(self.guard_timeout, ())
            logger.info("Started timeout guard")
            logger.info("Initialized request %s" % request_id)
            self.state = self.__class__.STATE_INITIALIZED
        elif m.data == "EOS":
            if self.state != self.__class__.STATE_CANCELLING:
                self.decoder_pipeline.end_request()
                self.state = self.__class__.STATE_EOS_RECEIVED
        else:
            if self.state != self.__class__.STATE_CANCELLING:
                self.decoder_pipeline.process_data(m.data)


    def closed(self, code, reason=None):
        logging.info("Websocket closed() called")
        self.state = self.__class__.STATE_FINISHED

    def _on_word(self, word):
        self.last_decoder_message = time.time()
        if word != "<#s>":
            if len(self.partial_transcript) > 0:
                self.partial_transcript += " "
            self.partial_transcript += word
            event = dict(status=common.STATUS_SUCCESS,
                         result=dict(hypotheses=[dict(transcript=self.partial_transcript)], final=False))
            self.send(json.dumps(event))
        else:
            logger.info("Postprocessing final result..")
            final_transcript = self.post_process(self.partial_transcript)
            logger.info("Postprocessing done.")
            event = dict(status=common.STATUS_SUCCESS,
                         result=dict(hypotheses=[dict(transcript=final_transcript)], final=True))
            self.send(json.dumps(event))
            self.partial_transcript = ""



    def _on_eos(self, data=None):
        self.last_decoder_message = time.time()
        self.close()

    def post_process(self, text):
        if self.post_processor:
            self.post_processor.stdin.write("%s\n" % text)
            self.post_processor.stdin.flush()
            text = self.post_processor.stdout.readline()
            return text.strip()
        else:
            return text



def main():
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(message)s ")
    logging.debug('Starting up worker')
    parser = argparse.ArgumentParser(description='Worker for kaldigstserver')
    parser.add_argument('-u', '--uri', default="ws://localhost:8888/worker/ws/speech", dest="uri", help="Server<-->worker websocket URI")
    parser.add_argument('-f', '--fork', default=1, dest="fork", type=int)
    parser.add_argument('-c', '--conf', dest="conf", help="YAML file with decoder configuration")
    args = parser.parse_args()

    if args.fork > 1:
        import tornado.process

        logging.info("Forking into %d processes" % args.fork)
        tornado.process.fork_processes(args.fork)

    conf = {}
    if args.conf:
        with open(args.conf) as f:
            conf = yaml.safe_load(f)
    decoder_pipeline = DecoderPipeline(conf)

    post_processor = None
    if "post-processor" in conf:
        post_processor = Popen(conf["post-processor"], shell=True, stdin=PIPE, stdout=PIPE)

    loop = GObject.MainLoop()
    thread.start_new_thread(loop.run, ())
    while True:
        ws = ServerWebsocket(args.uri, decoder_pipeline, post_processor)
        try:
            ws.connect()
            ws.run_forever()
        except Exception:
            logger.error("Couldn't connect to server, waiting for %d seconds", CONNECT_TIMEOUT)
            sleep(CONNECT_TIMEOUT)




if __name__ == "__main__":
    main()

