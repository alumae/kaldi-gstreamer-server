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


import settings
import common


class Application(tornado.web.Application):
    def __init__(self):
        settings = dict(
            cookie_secret="43oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
            autoescape=None,
        )

        handlers = [
            (r"/", MainHandler),
            (r"/client/ws/speech", DecoderSocketHandler),
            (r"/client/ws/status", StatusSocketHandler),
            (r"/worker/ws/speech", WorkerSocketHandler),
            (r"/client/static/(.*)", tornado.web.StaticFileHandler, {'path': "static"}),
        ]
        tornado.web.Application.__init__(self, handlers, **settings)
        self._redis = redis.Redis()
        self._redis_namespace = options.namespace
        self.available_workers = set()
        self.status_listeners = set()
        self.num_requests_processed = 0

    def send_status_update_single(self, ws):
        status = dict(num_workers_available=len(self.available_workers), num_requests_processed=self.num_requests_processed)
        ws.write_message(json.dumps(status))

    def send_status_update(self):
        for ws in self.status_listeners:
            self.send_status_update_single(ws)



class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("../../README.md")

class StatusSocketHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        logging.info("New status listener")
        self.application.status_listeners.add(self)
        self.application.send_status_update_single(self)

    def on_close(self):
        logging.info("Status listener left")
        self.application.status_listeners.remove(self)




class WorkerSocketHandler(tornado.websocket.WebSocketHandler):
    def __init__(self, application, request, **kwargs):
        tornado.websocket.WebSocketHandler.__init__(self, application, request, **kwargs)
        self.client_socket = None

    def open(self):
        self.client_socket = None
        self.application.available_workers.add(self)
        logging.info("New worker available " + self.__str__())
        self.application.send_status_update()

    def on_close(self):
        logging.info("Worker " + self.__str__() + " leaving")
        self.application.available_workers.discard(self)
        if self.client_socket:
            self.client_socket.close()
        self.application.send_status_update()

    def on_message(self, message):
        assert self.client_socket is not None
        event = json.loads(message)
        self.client_socket.send_event(event)

    def set_client_socket(self, client_socket):
        self.client_socket = client_socket



class DecoderSocketHandler(tornado.websocket.WebSocketHandler):

    def send_event(self, event):
        logging.info("%s: Sending event %s to client" % (self.id, event))
        self.write_message(json.dumps(event))

    def open(self):
        self.id = str(uuid.uuid4())
        logging.info("%s: OPEN" % self.id)
        self.worker = None
        try:
            self.worker = self.application.available_workers.pop()
            self.application.send_status_update()
            logging.info("%s: Using worker %s" % (self.id, self.__str__()))
            self.worker.set_client_socket(self)

            content_type = self.get_argument("content-type", None, True)
            if content_type:
                logging.info("%s: Using content type: %s" % (self.id, content_type))
            self.worker.write_message(json.dumps(dict(id=self.id, content_type=content_type)))
        except KeyError:
            logging.warn("%s: No worker available for client request" % self.id)
            event = dict(status=common.STATUS_NOT_AVAILABLE, message="No decoder available, try again later")
            self.send_event(event)
            self.close()

    def on_connection_close(self):
        logging.info("%s: Handling on_connection_close()" % self.id)
        self.application.num_requests_processed += 1
        self.application.send_status_update()
        if self.worker:
            try:
                self.worker.set_client_socket(None)
                self.worker.close()
            except:
                pass

    def on_message(self, message):
        assert self.worker is not None
        logging.info("%s: Forwarding client message of length %d to worker" % (self.id, len(message)))
        self.worker.write_message(message, binary=True)


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

    