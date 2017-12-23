import codecs
import logging
import time

import tornado.web


class ReferenceHandler(tornado.web.RequestHandler):
    def post(self, *args, **kwargs):
        content_id = self.request.headers.get("Content-Id")
        if content_id:
            content = codecs.decode(self.request.body, "utf-8")
            user_id = self.request.headers.get("User-Id", "")
            self.application.save_reference(content_id,
                                            dict(content=content,
                                                 user_id=user_id,
                                                 time=time.strftime(
                                                     "%Y-%m-%dT%H:%M:%S")))
            logging.info("Received reference text for content %s and user %s"
                         % (content_id, user_id))
            self.set_header('Access-Control-Allow-Origin', '*')
        else:
            self.set_status(400)
            self.finish("No Content-Id specified")

    def options(self, *args, **kwargs):
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.set_header('Access-Control-Max-Age', 1000)
        # note that '*' is not valid for Access-Control-Allow-Headers
        self.set_header('Access-Control-Allow-Headers',
                        'origin, x-csrftoken, content-type, accept,\
 User-Id, Content-Id')
