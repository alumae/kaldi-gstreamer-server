import argparse
import time
import sys
import urllib


def rate_limited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)

    def decorate(func):
        lastTimeCalled = [0.0]

        def rate_limited_function(*args, **kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait > 0:
                time.sleep(leftToWait)
            ret = func(*args, **kargs)
            lastTimeCalled[0] = time.clock()
            return ret
        return rate_limited_function
    return decorate


def main():
    parser = argparse.ArgumentParser(
        description='Command line client for kaldigstserver')
    parser.add_argument('-u', '--uri',
                        default="ws://localhost:8888/client/ws/speech",
                        dest="uri", help="Server websocket URI")
    parser.add_argument('-r', '--rate', default=32000, dest="rate", type=int,
                        help="Rate in bytes/sec at which audio should be sent to the server.\
 NB! For raw 16-bit audio it must be 2*samplerate!")
    parser.add_argument('--save-adaptation-state',
                        help="Save adaptation state to file")
    parser.add_argument('--send-adaptation-state',
                        help="Send adaptation state from file")
    parser.add_argument('--content-type', default='',
                        help="Use the specified content type (empty by default,\
 for raw files the default is  audio/x-raw, layout=(string)interleaved,\
 rate=(int)<rate>, format=(string)S16LE, channels=(int)1")
    parser.add_argument('audiofile', help="Audio file to be\
 sent to the server", type=argparse.FileType('rb'), default=sys.stdin)
    args = parser.parse_args()

    content_type = args.content_type
    if content_type == '' and args.audiofile.name.endswith(".raw"):
        content_type = "audio/x-raw, layout=(string)interleaved, rate=(int)%d,\
 format=(string)S16LE, channels=(int)1" % (args.rate/2)

    ws = MyClient(args.audiofile, args.uri + '?%s' %
                  (urllib.urlencode([("content-type", content_type)])),
                  byterate=args.rate,
                  save_adaptation_state_filename=args.save_adaptation_state,
                  send_adaptation_state_filename=args.send_adaptation_state)
    ws.connect()
    result = ws.get_full_hyp()
    print(result.encode('utf-8'))

if __name__ == "__main__":
    main()
