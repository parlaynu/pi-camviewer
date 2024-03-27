#!/usr/bin/env python3
import argparse
import io
import os
import re
import time
import json
from itertools import islice
from datetime import datetime
import piexif
import zmq

from PIL import Image
import numpy as np

from rcam import RCamClient
from rcam.server import PubSubCommands


def connect(zmq_context, url):
    # connect to the server
    sub_sock = zmq_context.socket(zmq.SUB)
    sub_sock.set_hwm(2)
    sub_sock.connect(url)
    sub_sock.setsockopt(zmq.SUBSCRIBE, b'')

    metadata = None

    while True:
        mask = sub_sock.poll(flags=zmq.POLLIN)
        if mask == 0:
            continue
        
        tag, idx, data = sub_sock.recv_multipart()

        idx = int(idx.decode('utf-8'))

        if tag == PubSubCommands.METADATA:
            metadata = json.loads(data.decode('utf-8'))
        
        elif metadata is not None and tag == PubSubCommands.JPEGIMG:
            image_id = f'img-{idx:04d}'
            
            jpeg = io.BytesIO(data)
            image = np.array(Image.open(jpeg))
            
            item = {
                'idx': idx,
                'image': image,
                'metadata': metadata
            }
            yield item
    
    sub_sock.disconnect(self.pub_url)


def drop(pipe, drop):
    start = 0
    for item in pipe:
        if item['idx'] - start < drop:
            continue
        start = item['idx']
        
        yield item


def generate_exif(pipe):
    for item in pipe:
        metadata = item['metadata']
        cam_model = metadata.get('CameraModel', 'unknown')
        
        datetime_now = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
        zero_ifd = {
            piexif.ImageIFD.Make: "Raspberry Pi",
            piexif.ImageIFD.Model: cam_model,
            piexif.ImageIFD.Software: "Picamera2",
            piexif.ImageIFD.DateTime: datetime_now
        }
        total_gain = metadata["AnalogueGain"] * metadata["DigitalGain"]
        exif_ifd = {
            piexif.ExifIFD.DateTimeOriginal: datetime_now,
            piexif.ExifIFD.ExposureTime: (metadata["ExposureTime"], 1000000),
            piexif.ExifIFD.ISOSpeedRatings: int(total_gain * 100)
        }
        exif = piexif.dump({"0th": zero_ifd, "Exif": exif_ifd})

        item['exif'] = exif
        
        yield item


def save_metadata(pipe, save_dir):
    for item in pipe:
        idx = item['idx']
        metadata = item['metadata'].copy()
        
        # don't save any stats for the camera
        for k in list(metadata.keys()):
            if k.endswith('StatsOutput'):
                del metadata[k]
        
        md_path = os.path.join(save_dir, f"img-{idx:04d}.json")
        print(f"saving to {md_path}")
        
        with open(md_path, "w") as f:
            print(json.dumps(metadata, sort_keys=True, indent=2), file=f)

        yield item


def save_image(pipe, outdir, *, format='png'):
    for item in pipe:
        idx = item['idx']
        
        image = item['image']
        exif = item.get('exif', None)

        img_path = os.path.join(outdir, f"img-{idx:04d}.{format}")

        print(f"saving to {img_path}")
        image = Image.fromarray(image)
        image.save(img_path, quality=95, exif=exif)

        yield item

    
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--num-images', help='number of images to capture', type=int, default=10)
    parser.add_argument('-d', '--drop', help='images to drop between captures (approx)', type=int, default=10)
    parser.add_argument('save_dir', help='directory to save images to', type=str)
    parser.add_argument('api_url', help='the api url to connect to', type=str)
    args = parser.parse_args()
    
    # derive the publish url from the api url
    tcp_re = re.compile("^tcp://(?P<address>.+?):(?P<port>\d+)$")
    mo = tcp_re.match(args.api_url)
    if mo is None:
        raise ValueError(f"unable to parse {args.api_url}")
    address = mo['address']
    port = int(mo['port'])

    pub_url = f"tcp://{address}:{port+1}"
    
    # create an api client and make sure no cropping or scaling is happening
    zmq_context = zmq.Context()
    client = RCamClient(zmq_context, args.api_url)
    client.fit_none()
    
    # prepare the output directory
    args.save_dir = os.path.join(args.save_dir, f"{int(time.time())}")
    os.makedirs(args.save_dir)
    
    # build the pipeline
    pipe = connect(zmq_context, pub_url)
    pipe = drop(pipe, args.drop)
    pipe = generate_exif(pipe)
    pipe = save_metadata(pipe, args.save_dir)
    pipe = save_image(pipe, args.save_dir)
    
    for item in islice(pipe, args.num_images):
        pass


if __name__ == "__main__":
    main()
