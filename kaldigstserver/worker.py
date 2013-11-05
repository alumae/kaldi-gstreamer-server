'''
Created on Jun 6, 2013

@author: tanel

Worker process: reads speech data from Redis, forwards to decoder, reads results from decoder, puts to Redis 
'''
import logging
import time
import thread
import argparse
import datetime
from subprocess import Popen, PIPE
from gi.repository import GObject, Gst
import yaml
import json

import redis

from decoder import DecoderPipeline
import common


logger = logging.getLogger(__name__)

_redis = None
_redis_namespace = "speech_dev"

CHUNK_TIMEOUT = 10
TIMEOUT_DECODER = 5
EXPIRE_RESULTS = 10


class RequestProcessor:
    def __init__(self, request_id, decoder_pipeline, post_processor=None):
        self.request_id = request_id
        self.decoder_pipeline = decoder_pipeline
        self.post_processor = post_processor
        self.last_decoder_message = time.time()
        self.partial_transcript = ""
        self.finished = False

    def _on_word(self, word):
        self.last_decoder_message = time.time()
        if word != "<#s>":
            if len(self.partial_transcript) > 0:
                self.partial_transcript += " "
            self.partial_transcript += word
            event = dict(status=common.STATUS_SUCCESS,
                         result=dict(hypotheses=[dict(transcript=self.partial_transcript)], final=False))
            _redis.rpush("%s:%s:speech_recognition_event" % (_redis_namespace, self.request_id), json.dumps(event))
        else:
            logger.info("Postprocessing final result..")
            final_transcript = self.post_process(self.partial_transcript)
            logger.info("Postprocessing done.")
            event = dict(status=common.STATUS_SUCCESS,
                         result=dict(hypotheses=[dict(transcript=final_transcript)], final=True))
            _redis.rpush("%s:%s:speech_recognition_event" % (_redis_namespace, self.request_id), json.dumps(event))
            self.partial_transcript = ""


    def _on_eos(self, data=None):
        self.last_decoder_message = time.time()
        event = dict(status=common.STATUS_EOS)
        _redis.rpush("%s:%s:speech_recognition_event" % (_redis_namespace, self.request_id), json.dumps(event))
        _redis.expire("%s:%s:speech_recognition_event" % (_redis_namespace, self.request_id), EXPIRE_RESULTS)

        self.finished = True

    def post_process(self, text):
        if self.post_processor:
            self.post_processor.stdin.write("%s\n" % text)
            self.post_processor.stdin.flush()
            text = self.post_processor.stdout.readline()
            return text.strip()
        else:
            return text

    def run(self):
        self.decoder_pipeline.set_word_handler(self._on_word)
        self.decoder_pipeline.set_eos_handler(self._on_eos)
        content_type = _redis.get("%s:%s:content_type" % (_redis_namespace, self.request_id))
        logger.info("Using content type %s" % content_type)

        self.decoder_pipeline.init_request(self.request_id, content_type)
        while True:
            rval = _redis.blpop("%s:%s:speech" % (_redis_namespace, self.request_id), CHUNK_TIMEOUT)
            if rval:
                (key, data) = rval
                if data == "__EOS__":
                    self.decoder_pipeline.end_request()
                    break
                else:
                    self.decoder_pipeline.process_data(data)
            else:
                logging.info("Timeout occurred for %s. Stopping processing." % self.request_id)
                self._on_eos()
                self.decoder_pipeline.cancel()
                return

        while not self.finished:
            if time.time() - self.last_decoder_message > TIMEOUT_DECODER:
                logger.warning("More than %d seconds from last decoder activity, cancelling" % TIMEOUT_DECODER)
                decoder_pipeline.cancel()
                self._on_eos()
                return
            logger.info("Waiting for decoder end")
            time.sleep(1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(message)s ")
    parser = argparse.ArgumentParser(description='Worker for kaldigstserver')
    parser.add_argument('-n', '--namespace', default="speech_dev", dest="namespace")
    parser.add_argument('-s', '--host', default="localhost", dest="host")
    parser.add_argument('-p', '--port', default=6379, dest="port", type=int)
    parser.add_argument('-f', '--fork', default=1, dest="fork", type=int)
    parser.add_argument('-c', '--conf', dest="conf", help="YAML file with decoder configuration")
    args = parser.parse_args()

    if args.fork > 1:
        import tornado.process

        logging.info("Forking into %d processes" % args.fork)
        tornado.process.fork_processes(args.fork)

    _redis_namespace = args.namespace
    _redis = redis.Redis(host=args.host, port=args.port)

    conf = {}
    if args.conf:
        with open(args.conf) as f:
            conf = yaml.safe_load(f)
    decoder_pipeline = DecoderPipeline(conf)

    post_processor = None
    if "post-processor" in conf:
        post_processor = Popen(conf["post-processor"], shell=True, stdin=PIPE, stdout=PIPE)

    logger.debug("Using namespace %s" % _redis_namespace)
    loop = GObject.MainLoop()
    thread.start_new_thread(loop.run, ())
    while True:
        logger.info("Waiting for request to handle")

        (key, request_id) = _redis.blpop("%s:requests" % _redis_namespace)
        logger.info("Starting to process request %s" % request_id)
        processor = RequestProcessor(request_id=request_id, decoder_pipeline=decoder_pipeline,
                                     post_processor=post_processor)
        processor.run()

    