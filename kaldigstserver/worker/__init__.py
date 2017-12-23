import argparse
import base64
import codecs
import json
import locale
import logging
import logging.config
import sys
import _thread
import time
import zlib
from subprocess import PIPE, Popen

import tornado.process
import ws4py.messaging
import yaml
from decoder import DecoderPipeline
from decoder2 import DecoderPipeline2
from gi.repository import GObject
from ws4py.client.threadedclient import WebSocketClient

CONNECT_TIMEOUT = 5
SILENCE_TIMEOUT = 5
USE_NNET2 = False

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

    if "logging" in conf:
        logging.config.dictConfig(conf["logging"])

    # fork off the post-processors before we load the model into memory
    post_processor = None
    if "post-processor" in conf:
        post_processor = Popen(conf["post-processor"], shell=True, stdin=PIPE, stdout=PIPE)

    full_post_processor = None
    if "full-post-processor" in conf:
        full_post_processor = Popen(conf["full-post-processor"], shell=True, stdin=PIPE, stdout=PIPE)

    global USE_NNET2
    USE_NNET2 = conf.get("use-nnet2", False)

    global SILENCE_TIMEOUT
    SILENCE_TIMEOUT = conf.get("silence-timeout", 5)
    if USE_NNET2:
        decoder_pipeline = DecoderPipeline2(conf)
    else:
        decoder_pipeline = DecoderPipeline(conf)


    loop = GObject.MainLoop()
    thread.start_new_thread(loop.run, ())
    while True:
        ws = ServerWebsocket(args.uri, decoder_pipeline, post_processor, full_post_processor=full_post_processor)
        try:
            logger.info("Opening websocket connection to master server")
            ws.connect()
            ws.run_forever()
        except Exception:
            logger.error("Couldn't connect to server, waiting for %d seconds", CONNECT_TIMEOUT)
            time.sleep(CONNECT_TIMEOUT)
        # fixes a race condition
        time.sleep(1)

if __name__ == "__main__":
    main()
