#!/usr/bin/env python
#
# Copyright 2013 Tanel Alumae

"""
Reads speech data via websocket requests, sends it to Redis, waits for results from Redis and
forwards to client via websocket
"""
import sys
import threading
import time
import logging
import datetime
import json

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
import common

#logging = logging.getlogging(__name__)




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
        self.render("../../README.md")


class DecoderSocketHandler(tornado.websocket.WebSocketHandler):
    def _send_word(self, word):
        logging.info("%s: Sending word %s to client" % (self.id, word))
        self.write_message(word)

    def _close(self):
        logging.info("%s: Closing client connection" % self.id)
        self.close()

    def _send_event(self, event):
        logging.info("%s: Sending event %s to client" % (self.id, event))
        self.write_message(json.dumps(event))

    def _poll_for_words(self):

        while True:
            logging.debug("%s: Polling redis for words" % self.id)
            rval = self.application._redis.blpop("%s:%s:speech_recognition_event" % (self.application._redis_namespace, self.id),
                                                 timeout=self.timeout)
            logging.info("%s: Got event: %s" % (self.id, rval))
            if rval:
                (key, event_json) = rval
                event = json.loads(event_json)
                if event["status"] == common.STATUS_SUCCESS:
                    self._send_event(event)
                elif event["status"] == common.STATUS_EOS:
                    self._close()
                else:
                    self._send_event(event)
                    self._close()
            else:
                logging.warning("%s: No words received in last %d seconds, giving up" % (self.id, self.timeout))
                #TODO: send something 1st?
                self._close()
                return

    def _clean_pending(self):
        logging.debug("%s: Cleaning pending speech data" % self.id)
        self.application._redis.delete("%s:%s:speech_recognition_event" % (self.application._redis_namespace, self.id))
        self.application._redis.delete("%s:%s:speech" % (self.application._redis_namespace, self.id))

    def open(self):
        self.id = str(uuid.uuid4())
        self.total_length = 0
        self.timeout = 10
        logging.info("%s: OPEN" % self.id)
        content_type = self.get_argument("content-type", None, True)
        if content_type:
            logging.info("%s: Using content type: %s" % (self.id, content_type))
            self.application._redis.set("%s:%s:content_type" % (self.application._redis_namespace, self.id), content_type)
            self.application._redis.expire("%s:%s:content_type" % (self.application._redis_namespace, self.id), self.timeout)
        self.application._redis.rpush("%s:requests" % self.application._redis_namespace, self.id)

        t = threading.Thread(target=self._poll_for_words)
        t.daemon = True
        t.start()
        logging.info("%s: Opened connection" % self.id)

    def on_close(self):
        logging.info("%s: Handling on_close()" % self.id)
        self._clean_pending()

    def on_message(self, message):
        if message == "EOS":
            logging.debug("%s: EOS from client after %d bytes" % (self.id, self.total_length))
            self.application._redis.rpush("%s:%s:speech" % (self.application._redis_namespace, self.id), "__EOS__")
        else:
            logging.debug("%s: Received %d bytes" % (self.id, len(message)))
            self.total_length += len(message)
            self.application._redis.rpush("%s:%s:speech" % (self.application._redis_namespace, self.id), message)
        self.application._redis.expire("%s:%s:speech" % (self.application._redis_namespace, self.id), self.timeout)


def main():
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(message)s ")
    logging.debug('Starting up server')
    from tornado.options import options

    tornado.options.parse_command_line()
    app = Application()
    app.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()

    