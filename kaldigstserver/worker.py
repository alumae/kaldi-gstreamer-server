__author__ = 'tanel'

import logging
import logging.config
import time
import thread
import threading
import os
import argparse
from subprocess import Popen, PIPE
from gi.repository import GObject
import yaml
import json
import sys
import locale
import codecs
import zlib
import base64
import time

import tornado.gen 
import tornado.process
import tornado.ioloop
import tornado.locks
from ws4py.client.threadedclient import WebSocketClient
import ws4py.messaging

from decoder import DecoderPipeline
from decoder2 import DecoderPipeline2

import common

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5
SILENCE_TIMEOUT = 5
USE_NNET2 = False

        
class ServerWebsocket(WebSocketClient):
    STATE_CREATED = 0
    STATE_CONNECTED = 1
    STATE_INITIALIZED = 2
    STATE_PROCESSING = 3
    STATE_EOS_RECEIVED = 7
    STATE_CANCELLING = 8
    STATE_FINISHED = 100

    def __init__(self, uri, decoder_pipeline, post_processor, full_post_processor=None):
        self.uri = uri
        self.decoder_pipeline = decoder_pipeline
        self.post_processor = post_processor
        self.full_post_processor = full_post_processor
        WebSocketClient.__init__(self, url=uri, heartbeat_freq=10)
        self.pipeline_initialized = False
        self.partial_transcript = ""
        if USE_NNET2:
            self.decoder_pipeline.set_result_handler(self._on_result)
            self.decoder_pipeline.set_full_result_handler(self._on_full_result)
            self.decoder_pipeline.set_error_handler(self._on_error)
        else:
            self.decoder_pipeline.set_word_handler(self._on_word)
            self.decoder_pipeline.set_error_handler(self._on_error)
        self.decoder_pipeline.set_eos_handler(self._on_eos)
        self.state = self.STATE_CREATED
        self.last_decoder_message = time.time()
        self.request_id = "<undefined>"
        self.timeout_decoder = 5
        self.num_segments = 0
        self.last_partial_result = ""
        self.post_processor_lock = tornado.locks.Lock()
        self.processing_condition = tornado.locks.Condition()
        self.num_processing_threads = 0
        
        
    def opened(self):
        logger.info("Opened websocket connection to server")
        self.state = self.STATE_CONNECTED
        self.last_partial_result = ""
    
    def guard_timeout(self):
        global SILENCE_TIMEOUT
        while self.state in [self.STATE_EOS_RECEIVED, self.STATE_CONNECTED, self.STATE_INITIALIZED, self.STATE_PROCESSING]:
            if time.time() - self.last_decoder_message > SILENCE_TIMEOUT:
                logger.warning("%s: More than %d seconds from last decoder hypothesis update, cancelling" % (self.request_id, SILENCE_TIMEOUT))
                self.finish_request()
                event = dict(status=common.STATUS_NO_SPEECH)
                try:
                    self.send(json.dumps(event))
                except:
                    logger.warning("%s: Failed to send error event to master" % (self.request_id))
                self.close()
                return
            logger.debug("%s: Checking that decoder hasn't been silent for more than %d seconds" % (self.request_id, SILENCE_TIMEOUT))
            time.sleep(1)

    def received_message(self, m):
        logger.debug("%s: Got message from server of type %s" % (self.request_id, str(type(m))))
        if self.state == self.__class__.STATE_CONNECTED:
            props = json.loads(str(m))
            content_type = props['content_type']
            self.request_id = props['id']
            self.num_segments = 0
            self.decoder_pipeline.init_request(self.request_id, content_type)
            self.last_decoder_message = time.time()
            thread.start_new_thread(self.guard_timeout, ())
            logger.info("%s: Started timeout guard" % self.request_id)
            logger.info("%s: Initialized request" % self.request_id)
            self.state = self.STATE_INITIALIZED
        elif m.data == "EOS":
            if self.state != self.STATE_CANCELLING and self.state != self.STATE_EOS_RECEIVED and self.state != self.STATE_FINISHED:
                self.decoder_pipeline.end_request()
                self.state = self.STATE_EOS_RECEIVED
            else:
                logger.info("%s: Ignoring EOS, worker already in state %d" % (self.request_id, self.state))
        else:
            if self.state != self.STATE_CANCELLING and self.state != self.STATE_EOS_RECEIVED and self.state != self.STATE_FINISHED:
                if isinstance(m, ws4py.messaging.BinaryMessage):
                    self.decoder_pipeline.process_data(m.data)
                    self.state = self.STATE_PROCESSING
                elif isinstance(m, ws4py.messaging.TextMessage):
                    props = json.loads(str(m))
                    if 'adaptation_state' in props:
                        as_props = props['adaptation_state']
                        if as_props.get('type', "") == "string+gzip+base64":
                            adaptation_state = zlib.decompress(base64.b64decode(as_props.get('value', '')))
                            logger.info("%s: Setting adaptation state to user-provided value" % (self.request_id))
                            self.decoder_pipeline.set_adaptation_state(adaptation_state)
                        else:
                            logger.warning("%s: Cannot handle adaptation state type " % (self.request_id, as_props.get('type', "")))
                    else:
                        logger.warning("%s: Got JSON message but don't know what to do with it" % (self.request_id))
            else:
                logger.info("%s: Ignoring data, worker already in state %d" % (self.request_id, self.state))

    def finish_request(self):
        if self.state == self.STATE_CONNECTED:
            # connection closed when we are not doing anything
            self.decoder_pipeline.finish_request()
            self.state = self.STATE_FINISHED
            return
        if self.state == self.STATE_INITIALIZED:
            # connection closed when request initialized but with no data sent
            self.decoder_pipeline.finish_request()
            self.state = self.STATE_FINISHED
            return
        if self.state != self.STATE_FINISHED:
            logger.info("%s: Master disconnected before decoder reached EOS?" % self.request_id)
            self.state = self.STATE_CANCELLING
            self.decoder_pipeline.cancel()
            counter = 0
            while self.state == self.STATE_CANCELLING:
                counter += 1
                if counter > 30:
                    # lost hope that the decoder will ever finish, likely it has hung
                    # FIXME: this might introduce new bugs
                    logger.info("%s: Giving up waiting after %d tries" % (self.request_id, counter))
                    self.state = self.STATE_FINISHED
                else:
                    logger.info("%s: Waiting for EOS from decoder" % self.request_id)
                    time.sleep(1)
            self.decoder_pipeline.finish_request()
            logger.info("%s: Finished waiting for EOS" % self.request_id)


    def closed(self, code, reason=None):
        logger.debug("%s: Websocket closed() called" % self.request_id)
        self.finish_request()
        logger.debug("%s: Websocket closed() finished" % self.request_id)

    @tornado.gen.coroutine
    def _increment_num_processing(self, delta):
        self.num_processing_threads += delta
        self.processing_condition.notify()

    @tornado.gen.coroutine
    def _on_result(self, result, final):
        try:
            self._increment_num_processing(1)
            if final:
                # final results are handled by _on_full_result()
                return
            self.last_decoder_message = time.time()
            if self.last_partial_result == result:
                return
            self.last_partial_result = result
            logger.info("%s: Postprocessing (final=%s) result.."  % (self.request_id, final))
            processed_transcripts = yield self.post_process([result], blocking=False)
            if processed_transcripts:
                logger.info("%s: Postprocessing done." % self.request_id)
                event = dict(status=common.STATUS_SUCCESS,
                             segment=self.num_segments,
                             result=dict(hypotheses=[dict(transcript=processed_transcripts[0])], final=final))
                try:
                    self.send(json.dumps(event))
                except:
                    e = sys.exc_info()[1]
                    logger.warning("Failed to send event to master: %s" % e)
        finally:
            self._increment_num_processing(-1)
    
    @tornado.gen.coroutine                     
    def _on_full_result(self, full_result_json):
        try:
            self._increment_num_processing(1)
            
            self.last_decoder_message = time.time()
            full_result = json.loads(full_result_json)
            full_result['segment'] = self.num_segments
            full_result['id'] = self.request_id
            if full_result.get("status", -1) == common.STATUS_SUCCESS:
                logger.debug(u"%s: Before postprocessing: %s" % (self.request_id, repr(full_result).decode("unicode-escape")))
                full_result = yield self.post_process_full(full_result)
                logger.info("%s: Postprocessing done." % self.request_id)
                logger.debug(u"%s: After postprocessing: %s" % (self.request_id, repr(full_result).decode("unicode-escape")))

                try:
                    self.send(json.dumps(full_result))
                except:
                    e = sys.exc_info()[1]
                    logger.warning("Failed to send event to master: %s" % e)
                if full_result.get("result", {}).get("final", True):
                    self.num_segments += 1
                    self.last_partial_result = ""
            else:
                logger.info("%s: Result status is %d, forwarding the result to the server anyway" % (self.request_id, full_result.get("status", -1)))
                try:
                    self.send(json.dumps(full_result))
                except:
                    e = sys.exc_info()[1]
                    logger.warning("Failed to send event to master: %s" % e)
        finally:
            self._increment_num_processing(-1)
    
    @tornado.gen.coroutine
    def _on_word(self, word):
        try:
            self._increment_num_processing(1)
            
            self.last_decoder_message = time.time()
            if word != "<#s>":
                if len(self.partial_transcript) > 0:
                    self.partial_transcript += " "
                self.partial_transcript += word
                logger.debug("%s: Postprocessing partial result.."  % self.request_id)
                processed_transcript = (yield self.post_process([self.partial_transcript], blocking=False))[0]
                if processed_transcript:
                    logger.debug("%s: Postprocessing done." % self.request_id)

                    event = dict(status=common.STATUS_SUCCESS,
                                 segment=self.num_segments,
                                 result=dict(hypotheses=[dict(transcript=processed_transcript)], final=False))
                    self.send(json.dumps(event))
            else:
                logger.info("%s: Postprocessing final result.."  % self.request_id)
                processed_transcript = (yield self.post_process(self.partial_transcript, blocking=True))
                logger.info("%s: Postprocessing done." % self.request_id)
                event = dict(status=common.STATUS_SUCCESS,
                             segment=self.num_segments,
                             result=dict(hypotheses=[dict(transcript=processed_transcript)], final=True))
                self.send(json.dumps(event))
                self.partial_transcript = ""
                self.num_segments += 1
        finally:
            self._increment_num_processing(-1)

    @tornado.gen.coroutine
    def _on_eos(self, data=None):
        self.last_decoder_message = time.time()
        # Make sure we won't close the connection before the 
        # post-processing has finished
        while self.num_processing_threads > 0:
            logging.debug("Waiting until processing threads finish (%d)" % self.num_processing_threads)
            yield self.processing_condition.wait()
        
        self.state = self.STATE_FINISHED
        self.send_adaptation_state()
        self.close()

    def _on_error(self, error):
        self.state = self.STATE_FINISHED
        event = dict(status=common.STATUS_NOT_ALLOWED, message=error)
        try:
            self.send(json.dumps(event))
        except:
            e = sys.exc_info()[1]
            logger.warning("Failed to send event to master: %s" % e)
        self.close()

    def send_adaptation_state(self):
        if hasattr(self.decoder_pipeline, 'get_adaptation_state'):
            logger.info("%s: Sending adaptation state to client..." % (self.request_id))
            adaptation_state = self.decoder_pipeline.get_adaptation_state()
            event = dict(status=common.STATUS_SUCCESS,
                         adaptation_state=dict(id=self.request_id,
                                               value=base64.b64encode(zlib.compress(adaptation_state)),
                                               type="string+gzip+base64",
                                               time=time.strftime("%Y-%m-%dT%H:%M:%S")))
            try:
                self.send(json.dumps(event))
            except:
                e = sys.exc_info()[1]
                logger.warning("Failed to send event to master: " + str(e))
        else:
            logger.info("%s: Adaptation state not supported by the decoder, not sending it." % (self.request_id))    

    @tornado.gen.coroutine
    def post_process(self, texts, blocking=False):
        if self.post_processor:
            logging.debug("%s: Waiting for postprocessor lock" % self.request_id)
            if blocking:
                timeout=None
            else:
                timeout=0.0
            try:
                with (yield self.post_processor_lock.acquire(timeout)):
                    result = []
                    for text in texts:
                        self.post_processor.stdin.write("%s\n" % text.encode("utf-8"))
                        self.post_processor.stdin.flush()
                        logging.debug("%s: Starting postprocessing: %s"  % (self.request_id, text))
                        text = yield self.post_processor.stdout.read_until('\n')
                        text = text.decode("utf-8")
                        logging.debug("%s: Postprocessing returned: %s"  % (self.request_id, text))
                        text = text.strip()
                        text = text.replace("\\n", "\n")
                        result.append(text)
                    raise tornado.gen.Return(result)
            except tornado.gen.TimeoutError:
                logging.debug("%s: Skipping postprocessing since post-processor already in use"  % (self.request_id))
                raise tornado.gen.Return(None)
        else:
            raise tornado.gen.Return(texts)
            
    @tornado.gen.coroutine
    def post_process_full(self, full_result):
        if self.full_post_processor:
            self.full_post_processor.stdin.write("%s\n\n" % json.dumps(full_result))
            self.full_post_processor.stdin.flush()
            lines = []
            while True:
                l = self.full_post_processor.stdout.readline()
                if not l: break # EOF
                if l.strip() == "":
                    break
                lines.append(l)
            full_result = json.loads("".join(lines))

        elif self.post_processor:
            transcripts = []
            for hyp in full_result.get("result", {}).get("hypotheses", []):
                transcripts.append(hyp["transcript"])
            processed_transcripts = yield self.post_process(transcripts, blocking=True)
            for (i, hyp) in enumerate(full_result.get("result", {}).get("hypotheses", [])):
                hyp["original-transcript"] = hyp["transcript"]
                hyp["transcript"] = processed_transcripts[i]
        raise tornado.gen.Return(full_result)        

def main_loop(uri, decoder_pipeline, post_processor, full_post_processor=None):
    while True:
        ws = ServerWebsocket(uri, decoder_pipeline, post_processor, full_post_processor=full_post_processor)
        try:
            logger.info("Opening websocket connection to master server")
            ws.connect()
            ws.run_forever()
        except Exception:
            logger.error("Couldn't connect to server, waiting for %d seconds", CONNECT_TIMEOUT)
            time.sleep(CONNECT_TIMEOUT)
        # fixes a race condition
        time.sleep(1)



def main():
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(message)s ")
    logging.debug('Starting up worker')
    parser = argparse.ArgumentParser(description='Worker for kaldigstserver')
    parser.add_argument('-u', '--uri', default="ws://localhost:8888/worker/ws/speech", dest="uri", help="Server<-->worker websocket URI")
    parser.add_argument('-f', '--fork', default=1, dest="fork", type=int)
    parser.add_argument('-c', '--conf', dest="conf", help="YAML file with decoder configuration")

    args = parser.parse_args()

    if args.fork > 1:
        logging.info("Forking into %d processes" % args.fork)
        tornado.process.fork_processes(args.fork)

    conf = {}
    if args.conf:
        with open(args.conf) as f:
            conf = yaml.safe_load(f)

    if "logging" in conf:
        logging.config.dictConfig(conf["logging"])

    # fork off the post-processors before we load the model into memory
    tornado.process.Subprocess.initialize()
    post_processor = None
    if "post-processor" in conf:
        STREAM = tornado.process.Subprocess.STREAM
        post_processor = tornado.process.Subprocess(conf["post-processor"], shell=True, stdin=PIPE, stdout=STREAM)
        

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
    thread.start_new_thread(main_loop, (args.uri, decoder_pipeline, post_processor, full_post_processor))  
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()

