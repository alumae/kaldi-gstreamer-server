#!/usr/bin/env python
#
# Copyright 2013 Tanel Alumae

"""Simplified chat demo for websockets.

Authentication, error handling, etc are left as an exercise for the reader :)
"""
import threading
import time
import logging
import tornado.escape
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket
import tornado.gen

import os.path
import uuid
import redis

from tornado.options import define, options

from decoder import DecoderPipeline

from Queue import Queue

import settings

logger = logging.getLogger(__name__)

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/speech", DecoderSocketHandler),
        ]
        settings = dict(
            cookie_secret="43oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
            autoescape=None,
        )
        tornado.web.Application.__init__(self, handlers, **settings)
        self._redis = redis.Redis()
        self._redis_namespace = options.namespace

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class DecoderSocketHandler(tornado.websocket.WebSocketHandler):
    def _send_word(self, word):
        logger.info("%s: Sending word %s to client" % (self.id, word))
        self.write_message(word)

    def _send_eos(self):
        logger.info("%s: Sending EOS to client" % self.id)
        self.close()
    
    def _poll_for_words(self):
        timeout = 10
        while True:
            logger.debug("%s: Polling redis for words" % self.id)
            rval = self.application._redis.blpop("%s:%s:text" % (self.application._redis_namespace, self.id), timeout=timeout)
            if rval:
                (key, word) = rval
                if word == "__EOS__":
                    self._send_eos()
                    break
                else:
                    self._send_word(word)
            else:
                logger.warning("%s: No words received in last %d seconds, giving up" % (self.id, timeout))
                self.close()
                return
            
    def _clean_pending(self):
        logger.debug("%s: Cleaning pending speech data" % self.id)
        self.application._redis.delete("%s:%s:speech" % (self.application._redis_namespace, self.id))
        
    def open(self):
        self.id = str(uuid.uuid4())
        self.total_length = 0
        logger.info("%s: OPEN" % self.id)
        self.application._redis.rpush("%s:requests" % self.application._redis_namespace , self.id)
        t = threading.Thread(target=self._poll_for_words)
        t.daemon = True
        t.start()
        logger.info("%s: Opened connection" % self.id)
        
    def on_close(self):
        logger.info("%s: Handling on_close()" % self.id)
        self._clean_pending()

    def on_message(self, message):
        if message == "EOS":
            logger.debug("%s: EOS from client after %d bytes" % (self.id, self.total_length))
            self.application._redis.rpush("%s:%s:speech" % (self.application._redis_namespace, self.id) , "__EOS__")
        else:
            self.total_length += len(message)
            self.application._redis.rpush("%s:%s:speech" % (self.application._redis_namespace, self.id) , message)

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)8s %(asctime)s %(message)s ")
    from tornado.options import options    
    tornado.options.parse_command_line()
    app = Application()
    app.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()

    