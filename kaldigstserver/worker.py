'''
Created on Jun 6, 2013

@author: tanel
'''
import redis
import logging
import time
import thread
import argparse
import sys

from gi.repository import GObject, Gst

from decoder import DecoderPipeline

logger = logging.getLogger(__name__)

_redis = None
_redis_namespace = "speech_dev"
decoder_pipeline = DecoderPipeline()


TIMEOUT = 1
TIMEOUT_DECODER = 3

def process(id):
    global last_decoder_message
    last_decoder_message = 0
    finished = [False]
    
    def _on_word(word):
        global last_decoder_message
        last_decoder_message = time.time()
        _redis.rpush("%s:%s:text" % (_redis_namespace, id) , word)

    def _on_eos(word):
        global last_decoder_message
        last_decoder_message = time.time()
        _redis.rpush("%s:%s:text" % (_redis_namespace, id) , "__EOS__")
        finished[0] = True

    decoder_pipeline.set_word_handler(_on_word)
    decoder_pipeline.set_eos_handler(_on_eos)
        
    decoder_pipeline.init_request(id, "audio/x-raw,rate=16000,channels=1,format=(string)S16LE")
    while True:
        rval = _redis.blpop("%s:%s:speech" % (_redis_namespace, id), TIMEOUT)
        if rval:
            (key, data) = rval
            if data == "__EOS__":
                decoder_pipeline.end_request()
                break
            else:
                decoder_pipeline.process_data(data)
        else:
            logging.info("Timeout occurred for %s. Stopping processing." % id)
            decoder_pipeline.cancel()
            return
            
    
    while not finished[0]:
        if time.time() - last_decoder_message > TIMEOUT_DECODER:
            logger.warning("More than %d seconds from last decoder activity, cancelling" % TIMEOUT_DECODER)
            decoder_pipeline.cancel()
            return
        logger.info("Waiting for decoder end")
        time.sleep(1)
    
            
        
def main_loop():
    while True:
        logger.info("Waiting for request to handle") 
        (key, id) = _redis.blpop("%s:requests" % _redis_namespace)
        logger.info("Starting to process request %s" % id)
        process(id)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(message)s ")
    parser = argparse.ArgumentParser(description='Worker for kaldigstserver')
    parser.add_argument('-n', '--namespace', default="speech_dev", dest="namespace")
    parser.add_argument('-s', '--host', default="localhost", dest="host")
    parser.add_argument('-p', '--port', default=6379, dest="port", type=int)
    args = parser.parse_args()
    _redis_namespace = args.namespace
    _redis = redis.Redis(host=args.host, port=args.port)
    logger.debug("Using namespace %s" % _redis_namespace)
    loop = GObject.MainLoop()
    thread.start_new_thread(loop.run, ())
    main_loop()
    