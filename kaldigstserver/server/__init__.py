import functools
import threading
import logging
import tornado.options
import tornado.ioloop


def run_async(func):
    @functools.wraps(func)
    def async_func(*args, **kwargs):
        func_hl = threading.Thread(target=func, args=args, kwargs=kwargs)
        func_hl.start()
        return func_hl

    return async_func


def content_type_to_caps(content_type):
    """
    Converts MIME-style raw audio content
    type specifier to GStreamer CAPS string
    """
    default_attributes = {"rate": 16000,
                          "format": "S16LE",
                          "channels": 1,
                          "layout": "interleaved"}
    media_type, _, attr_string = content_type.replace(";", ",").partition(",")
    if media_type in ["audio/x-raw", "audio/x-raw-int"]:
        media_type = "audio/x-raw"
        attributes = default_attributes
        for (key, _, value) in [p.partition("=")
                                for p in attr_string.split(",")]:
            attributes[key.strip()] = value.strip()
        return "%s, %s" % (media_type, ", ".join(
            ["%s=%s" % (key, value)
                for (key, value) in attributes.iteritems()]))
    else:
        return content_type


def main():
    logging.basicConfig(level=logging.DEBUG,
                        format="%(levelname)8s %(asctime)s %(message)s ")
    logging.debug('Starting up server')
    tornado.options.define("certfile", default="",
                           help="certificate file for secured SSL connection")
    tornado.options.define("keyfile", default="",
                           help="key file for secured SSL connection")

    tornado.options.parse_command_line()
    app = Application()
    if tornado.options.certfile and tornado.options.keyfile:
        ssl_options = {
          "certfile": tornado.options.certfile,
          "keyfile": tornado.options.keyfile,
        }
        logging.info("Using SSL for serving requests")
        app.listen(tornado.options.port, ssl_options=ssl_options)
    else:
        app.listen(tornado.options.port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
