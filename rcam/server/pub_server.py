from itertools import count
import threading
import zmq

from .operators import control, capture, jpeg_encoder, publisher
from .operators import focus, exposure, colour
from .operators import fit_scaled, fit_cropped


class PubServer(threading.Thread):
    def __init__(self, context, pub_url, svr_sockname, *, camera, ae_enabled):
        super().__init__()

        self.pub_sock = context.socket(zmq.PUB)
        self.pub_sock.set_hwm(2)
        self.pub_sock.bind(pub_url)
        
        self.svr_sock = context.socket(zmq.PAIR)
        self.svr_sock.connect(f"inproc://{svr_sockname}")
        
        self.ae_enabled = ae_enabled
        
        self.arrays = arrays = ["main"]
        self.camera = camera
        
    def run(self):
        print("pub_server: start")
        
        self.camera.start()

        pipe = control(self.svr_sock)
        pipe = capture(pipe, self.camera, self.arrays)
        pipe = focus(pipe, self.camera)
        pipe = exposure(pipe, self.camera)
        pipe = colour(pipe, self.camera)
        pipe = fit_cropped(pipe, enabled=False)
        pipe = fit_scaled(pipe, enabled=True)
        pipe = jpeg_encoder(pipe)
        pipe = publisher(pipe, self.pub_sock, self.svr_sock)
        
        for item in pipe:
            if item['controls'].get('Over', False):
                break

        print("pub_server: finish")

