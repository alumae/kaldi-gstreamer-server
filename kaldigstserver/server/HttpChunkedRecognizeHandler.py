import json
import logging
import uuid
from Queue import Queue

import tornado.gen
import tornado.web


@tornado.web.stream_request_body
class HttpChunkedRecognizeHandler(tornado.web.RequestHandler):
    """
    Provides a HTTP POST/PUT interface supporting chunked transfer requests,
    similar to that provided by
    http://github.com/alumae/ruby-pocketsphinx-server.
    """

    def prepare(self):
        self.id = str(uuid.uuid4())
        self.final_hyp = ""
        self.final_result_queue = Queue()
        self.user_id = self.request.headers.get("device-id", "none")
        self.content_id = self.request.headers.get("content-id", "none")
        logging.info("%s: OPEN: user='%s', content='%s'"
                     % (self.id, self.user_id, self.content_id))
        self.worker = None
        self.error_status = 0
        self.error_message = None
        try:
            self.worker = self.application.available_workers.pop()
            self.application.send_status_update()
            logging.info("%s: Using worker %s" % (self.id, self.__str__()))
            self.worker.set_client_socket(self)

            content_type = self.request.headers.get("Content-Type", None)
            if content_type:
                content_type = content_type_to_caps(content_type)
                logging.info("%s: Using content type: %s"
                             % (self.id, content_type))

            self.worker.write_message(json.dumps(
                                        dict(id=self.id,
                                             content_type=content_type,
                                             user_id=self.user_id,
                                             content_id=self.content_id)))
        except KeyError:
            logging.warn("%s: No worker available for client request"
                         % self.id)
            self.set_status(503)
            self.finish("No workers available")

    def data_received(self, chunk):
        assert self.worker is not None
        logging.debug("%s: Forwarding client message of length %d to worker"
                      % (self.id, len(chunk)))
        self.worker.write_message(chunk, binary=True)

    def post(self, *args, **kwargs):
        self.end_request(args, kwargs)

    def put(self, *args, **kwargs):
        self.end_request(args, kwargs)

    @run_async
    def get_final_hyp(self, callback=None):
        logging.info("%s: Waiting for final result..." % self.id)
        callback(self.final_result_queue.get(block=True))

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def end_request(self, *args, **kwargs):
        logging.info("%s: Handling the end of chunked recognize request"
                     % self.id)
        assert self.worker is not None
        self.worker.write_message("EOS", binary=True)
        logging.info("%s: yielding..." % self.id)
        hyp = yield tornado.gen.Task(self.get_final_hyp)
        if self.error_status == 0:
            logging.info("%s: Final hyp: %s" % (self.id, hyp))
            response = {"status": 0,
                        "id": self.id,
                        "hypotheses": [{"utterance": hyp}]}
            self.write(response)
        else:
            logging.info("%s: Error (status=%d) processing HTTP request: %s"
                         % (self.id, self.error_status, self.error_message))
            response = {"status": self.error_status,
                        "id": self.id,
                        "message": self.error_message}
            self.write(response)
        self.application.num_requests_processed += 1
        self.application.send_status_update()
        self.worker.set_client_socket(None)
        self.worker.close()
        self.finish()
        logging.info("Everything done")

    def send_event(self, event):
        event_str = str(event)
        if len(event_str) > 100:
            event_str = event_str[:97] + "..."
        logging.info("%s: Receiving event %s from worker"
                     % (self.id, event_str))
        if event["status"] == 0 and ("result" in event):
            try:
                if len(event["result"]["hypotheses"]) > 0 and \
                   event["result"]["final"]:
                    if len(self.final_hyp) > 0:
                        self.final_hyp += " "
                    self.final_hyp += (
                        event["result"]["hypotheses"][0]["transcript"])
            except:
                e = sys.exc_info()[0]
                logging.warn("Failed to extract hypothesis\
 from recognition result:" + e)
        elif event["status"] != 0:
            self.error_status = event["status"]
            self.error_message = event.get("message", "")

    def close(self):
        logging.info("%s: Receiving 'close' from worker" % (self.id))
        self.final_result_queue.put(self.final_hyp)
