Kaldi GStreamer server
======================

This is an implementation of a real-time full-duplex speech recognition server, based on
the Kaldi toolkit and the GStreamer framework.

Communication with the server is based on websockets. Client sends speech to the server using
small chunks, while the server sends partial and full recognition hypotheses back to
the client via the same websocket, thus enabling full-duplex communication (as in Google's
voice typing in Android).

Server usage
------------

### Opening a session

To open a session, connect to the specified server websocket address (e.g. ws://server:8888/speech).
The server assumes by deafult that incoming audio is sent using 16 kHz, mono, 16bit little-endian format. This can be overriden
using the 'content-type' request parameter. The content type has to be specified using GStreamer 1.0 caps format,
e.g. to send 44100 Hz mono 16-bit data, use: "audio/x-raw, layout=(string)interleaved, rate=(int)44100, format=(string)S16LE, channels=(int)1".
This needs to be url-encoded of course, so the actual request is something like:

    ws://server:8888/speech?content-type=audio/x-raw,+layout=(string)interleaved,+rate=(int)44100,+format=(string)S16LE,+channels=(int)1

Audio can also be encoded using any codec recognized by GStreamer (assuming the needed packages are installed on the server).
E.g., to send audio encoded using the Speex codec in an Ogg container, use the following URL to open the session (server should
automatically recognize the codec):

    ws://server:8888/speech?content-type=audio/ogg

### Sending audio

Speech should be sent to the server in raw blocks of data, using the encoding specified when session was opened.
It is recommended that a new block is sent at least 4 times per second (less infrequent blocks would increase the recognition lag).

After the last block of speech data, a special string "EOS"  ("end-of-stream") needs to be sent to the server. This tells the
server that no more speech is coming and the recognition can be finalized.

### Reading results

Server sends recognition results and other information to the client using the JSON format.
The response can contain the following fields:

  * status -- response status, see codes below
  * message -- (optional) status message
  * result -- (optional) recognition result, containing the followig fields:
    - hypotheses - recognized words, a list with each item containing the following:
        + transcript -- recognized words
        + confidence -- (optional) confidence of the hypothesis (float, 0..1)
    - final -- true when the hypothesis is final, i.e., doesn't change any more

The following status codes are currently in use:

  * 0 -- Success. Usually used when recognition results are sent
  * 2 -- Aborted. Recognition was aborted for some reason.
  * 1 -- No speech. Sent when the incoming audio contains a large portion of silence or non-speech.
  * 9 -- Not avalailable. Used when all recognizer processes are currently in use and recognition cannot be performed.

Websocket is always closed by the server after sending a non-zero status update.

Examples on server responses:

    {"status": 9}
    {"status": 0, "result": {"hypotheses": [{"transcript": "see on"}], "final": false}}
    {"status": 0, "result": {"hypotheses": [{"transcript": "see on teine lause."}], "final": true}}

Server segments incoming audio on the fly. For each segment, many non-final and one final
hypotheses are sent. Non-final hypotheses are used to present partial recognition hypotheses
to the client. A sequence of non-final hypotheses is always followed by a final hypothesis.
After sendig a final hypothesis,
server proceeds to the next segment or closes the connection, if the segment was last.
Client is reponsible for presenting the results to the user in a way
suitable for the application.

