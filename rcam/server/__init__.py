import uuid

from .api_server import ApiServer
from .pub_server import PubServer

from .camera import Camera
from .commands import ApiCommands, PubSubCommands


class Server:
    def __init__(self, context, api_url, pub_url, *, camera_id, mode, max_fps, exposure_time, analogue_gain, hflip, vflip, preview, tuning_file):

        svr_sockname = str(uuid.uuid4())
        
        cam = Camera(
            camera_id,
            mode,
            max_fps=max_fps,
            vflip=vflip,
            hflip=hflip,
            exposure_time=exposure_time,
            analogue_gain=analogue_gain,
            preview=preview,
            tuning_file=tuning_file
        )
        if preview:
            cam.start_preview_()
            
        min_ag, max_ag, _ = cam.camera_controls['AnalogueGain']
        min_et, max_et, _ = cam.camera_controls['ExposureTime']

        self.pub_svr = PubServer(context, pub_url, svr_sockname,
            camera=cam,
            ae_enabled=(exposure_time == 0)
        )
        self.api_svr = ApiServer(context, api_url, svr_sockname,
                min_ag=min_ag,
                max_ag=max_ag,
                min_et=min_et,
                max_et=max_et
        )

    def start(self):
        self.pub_svr.start()
        self.api_svr.start()

    def set_over(self):
        self.pub_svr.over = True
        self.api_svr.over = True

    def join(self):
        self.pub_svr.join()
        self.api_svr.join()

