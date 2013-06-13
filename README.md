Kaldi Gstreamer server
======================

Server usage
------------

Using the server is very easy:
  * open the websocket 
  * send chunks of binary speech data to the websocket (either raw or encoded, see below); the chunks should be sent at least once per second, otherwise the server assumes the client is "sleeping" and closes the connection
  * read recognized words from websocket (sent on word-by-word basis), with a special word "<#s>" marking sentence break
  * finally send the string "EOS" (""end-of-stream") to the websocket
  * when server closes the websocket, all data has been recognized and sent to the client
 
Speech data can be sent as raw or encoded. To send raw data, one has to specify the type of the raw data, using the "content-type" query parameter when opening the websocket. The content type has to be specified using GStreamer 1.0 caps format, e.g. to send 16000 Hz mono 16-bit data, use: "audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1". This needs to be url-encoded of course, so the actual request is something like:

    ws://server:8888/speech?content-type=audio/x-raw,+layout=(string)interleaved,+rate=(int)16000,+format=(string)S16LE,+channels=(int)1 
  
One can also send data that is already encoded in some known format (e.g., wav, mp3, ogg, speex, anything that GStreamer supports). In this case, you don't have to send the content type at all -- the server recognizes the encoding automatically.



