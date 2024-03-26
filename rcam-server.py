#!/usr/bin/env python3
import argparse
import zmq

import rcam
from rcam.server import Server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--api-port', help='port to bind api to', type=int, default=8089)
    parser.add_argument('-c', '--camera-id', help='the camera to connect to', type=int, default=0)
    parser.add_argument('-m', '--mode', help='the camera mode', type=int, default=2)
    parser.add_argument('-f', '--max-fps', help='the maximum fps', type=int, default=0)
    parser.add_argument('-e', '--exposure-time', help='the exposure time in microseconds', type=int, default=0)
    parser.add_argument('-g', '--analogue-gain', help='the analogue gain', type=float, default=0.0)
    parser.add_argument('--hflip', help='flip the image horizontally', action='store_true')
    parser.add_argument('--vflip', help='flip the image vertically', action='store_true')
    parser.add_argument('--preview', help='run the camera preview on attached monitor', action='store_true')
    args = parser.parse_args()
    
    api_url = f"tcp://0.0.0.0:{args.api_port}"
    pub_url = f"tcp://0.0.0.0:{args.api_port+1}"
    
    urls = rcam.connect_urls(api_url)
    for u in urls:
        print(f"listening at {u}")
    
    kwargs = vars(args)
    del kwargs['api_port']
    
    context = zmq.Context()
    svr = Server(context, api_url, pub_url, **kwargs)
    svr.start()
    
    try:
        svr.join()
    except KeyboardInterrupt:
        svr.set_over()
        svr.join()


if __name__ == "__main__":
    main()

