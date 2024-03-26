import zmq
from rcam.server import ApiCommands


class RCamClient:
    
    def __init__(self, zmq_context, api_url):
        self.api_sock = zmq_context.socket(zmq.PUSH)
        self.api_sock.connect(api_url)

    def shutdown(self):
        self.api_sock.send_multipart([ApiCommands.SHUTDOWN, b''])
        
    def set_size(self, width, height):
        body = f"{width}x{height}".encode('utf-8')
        self.api_sock.send_multipart([ApiCommands.SET_SIZE, body])

    def auto_exposure(self, state):
        if state:
            self.api_sock.send_multipart([ApiCommands.AUTOEXPOSURE_ENABLE, b''])
        else:
            self.api_sock.send_multipart([ApiCommands.AUTOEXPOSURE_DISABLE, b''])

    def gain_increase(self, locked):
        body = ApiCommands.EXPOSURE_LOCKED if locked else ApiCommands.EXPOSURE_UNLOCKED
        self.api_sock.send_multipart([ApiCommands.ANALOGUE_GAIN_INCREASE, body])
        
    def gain_decrease(self, locked):
        body = ApiCommands.EXPOSURE_LOCKED if locked else ApiCommands.EXPOSURE_UNLOCKED
        self.api_sock.send_multipart([ApiCommands.ANALOGUE_GAIN_DECREASE, body])

    def etime_increase(self, locked):
        body = ApiCommands.EXPOSURE_LOCKED if locked else ApiCommands.EXPOSURE_UNLOCKED
        self.api_sock.send_multipart([ApiCommands.EXPOSURE_TIME_INCREASE, body])

    def etime_decrease(self, locked):
        body = ApiCommands.EXPOSURE_LOCKED if locked else ApiCommands.EXPOSURE_UNLOCKED
        self.api_sock.send_multipart([ApiCommands.EXPOSURE_TIME_DECREASE, body])

    def auto_focus(self, state):
        if state:
            self.api_sock.send_multipart([ApiCommands.AUTOFOCUS_ENABLE, b''])
        else:
            self.api_sock.send_multipart([ApiCommands.AUTOFOCUS_DISABLE, b''])

    def run_autofocus(self):
        self.api_sock.send_multipart([ApiCommands.AUTOFOCUS_RUN, b''])
    
    def increase_lens_position(self):
        self.api_sock.send_multipart([ApiCommands.LENS_POSITION_INCREASE, b''])

    def decrease_lens_position(self):
        self.api_sock.send_multipart([ApiCommands.LENS_POSITION_DECREASE, b''])

    def fit_scaled(self):
        self.api_sock.send_multipart([ApiCommands.FIT_SCALED, b''])

    def fit_cropped(self):
        self.api_sock.send_multipart([ApiCommands.FIT_CROPPED, b''])

