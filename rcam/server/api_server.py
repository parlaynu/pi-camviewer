import time
import threading
import zmq

from .commands import ApiCommands


class ApiServer(threading.Thread):
    def __init__(self, context, api_url, svr_sockname, *, min_ag, max_ag, min_et, max_et):
        super().__init__()
        self.over = False
        self.api_sock = context.socket(zmq.PULL)
        self.api_sock.bind(api_url)
        
        self.svr_sock = context.socket(zmq.PAIR)
        self.svr_sock.bind(f"inproc://{svr_sockname}")
        
        self.analogue_gain = None
        self.exposure_time = None
        self.lens_position = None

        self.min_ag = min_ag
        self.max_ag = max_ag
        self.min_et = min_et
        self.max_et = max_et
        
        self.sock_handlers = {
            self.api_sock: self.handle_api_sock,
            self.svr_sock: self.handle_svr_sock
        }
        
        self.api_handlers = {
            ApiCommands.SHUTDOWN: self.handle_shutdown,
            ApiCommands.SET_SIZE: self.handle_set_size,
            ApiCommands.AUTOEXPOSURE_ENABLE: self.handle_ae_enable,
            ApiCommands.AUTOEXPOSURE_DISABLE: self.handle_ae_disable,
            ApiCommands.ANALOGUE_GAIN_INCREASE: self.handle_ag_increase,
            ApiCommands.ANALOGUE_GAIN_DECREASE: self.handle_ag_decrease,
            ApiCommands.EXPOSURE_TIME_INCREASE: self.handle_et_increase,
            ApiCommands.EXPOSURE_TIME_DECREASE: self.handle_et_decrease,
            ApiCommands.AUTOFOCUS_ENABLE: self.handle_af_enable,
            ApiCommands.AUTOFOCUS_DISABLE: self.handle_af_disable,
            ApiCommands.AUTOFOCUS_RUN: self.handle_af_run,
            ApiCommands.LENS_POSITION_INCREASE: self.handle_lp_increase,
            ApiCommands.LENS_POSITION_DECREASE: self.handle_lp_decrease,
            ApiCommands.FIT_SCALED: self.handle_fit_scaled,
            ApiCommands.FIT_CROPPED: self.handle_fit_cropped,
        }
        
    def run(self):
        print("api_server: start")
        
        poller = zmq.Poller()
        poller.register(self.api_sock, zmq.POLLIN)
        poller.register(self.svr_sock, zmq.POLLIN)
        
        while self.over == False:
            evs = poller.poll(timeout=200)
            for sock, _ in evs:
                self.sock_handlers[sock]()

        print("api_server: finish")

    def handle_api_sock(self):
        cmd, body = self.api_sock.recv_multipart()
        self.api_handlers[cmd](body)
    
    def handle_svr_sock(self):
        updates = self.svr_sock.recv_pyobj()
        self.exposure_time = updates.get('ExposureTime', self.exposure_time)
        self.analogue_gain = updates.get('AnalogueGain', self.analogue_gain)
        self.lens_position = updates.get('LensPosition', self.lens_position)

    def handle_shutdown(self, body):
        controls = {
            'Over': True
        }
        self.svr_sock.send_pyobj(controls)
        self.over = True
        
    def handle_set_size(self, body):
        body = body.decode('utf-8')
        width, height = [int(x) for x in body.split('x')]
        controls = {
            'Width': width,
            'Height': height
        }
        self.svr_sock.send_pyobj(controls)
    
    def handle_ae_enable(self, body):
        controls = {
            'AeEnable': True,
            'AwbEnable': True
        }
        self.svr_sock.send_pyobj(controls)
    
    def handle_ae_disable(self, body):
        controls = {
            'AeEnable': False,
            'AwbEnable': False
        }
        self.svr_sock.send_pyobj(controls)
        
    def handle_ag_increase(self, body):
        self.scale_exposure(ApiCommands.ANALOGUE_GAIN_INCREASE, body)
    
    def handle_ag_decrease(self, body):
        self.scale_exposure(ApiCommands.ANALOGUE_GAIN_DECREASE, body)
    
    def handle_et_increase(self, body):
        self.scale_exposure(ApiCommands.EXPOSURE_TIME_INCREASE, body)
    
    def handle_et_decrease(self, body):
        self.scale_exposure(ApiCommands.EXPOSURE_TIME_DECREASE, body)

    def scale_exposure(self, cmd, body):
        if self.exposure_time is None:
            return
        
        product = self.analogue_gain * self.exposure_time

        ag_scale = 2 ** 0.1
        et_scale = 2 ** 0.2
        
        if cmd == ApiCommands.ANALOGUE_GAIN_INCREASE:
            self.analogue_gain = min(self.analogue_gain * ag_scale, self.max_ag)
            if body == ApiCommands.EXPOSURE_LOCKED:
                self.exposure_time = int(max(product / self.analogue_gain, self.min_et))
        
        elif cmd == ApiCommands.ANALOGUE_GAIN_DECREASE:
            self.analogue_gain = max(self.analogue_gain / ag_scale, self.min_ag)
            if body == ApiCommands.EXPOSURE_LOCKED:
                self.exposure_time = int(min(product / self.analogue_gain, self.max_et))
    
        elif cmd == ApiCommands.EXPOSURE_TIME_INCREASE:
            self.exposure_time = min(int(self.exposure_time * et_scale), self.max_et)
            if body == ApiCommands.EXPOSURE_LOCKED:
                self.analogue_gain = max(product / self.exposure_time, self.min_ag)
    
        elif cmd == ApiCommands.EXPOSURE_TIME_DECREASE:
            self.exposure_time = max(int(self.exposure_time / et_scale), self.min_et)
            if body == ApiCommands.EXPOSURE_LOCKED:
                self.analogue_gain = min(product / self.exposure_time, self.max_ag)
        
        controls = {
            'AeEnable': False,
            'AwbEnable': False,
            'AnalogueGain': self.analogue_gain,
            'ExposureTime': self.exposure_time,
        }
        self.svr_sock.send_pyobj(controls)

    def handle_af_enable(self, body):
        controls = {
            'AfEnable': True
        }
        self.svr_sock.send_pyobj(controls)
    
    def handle_af_disable(self, body):
        controls = {
            'AfEnable': False
        }
        self.svr_sock.send_pyobj(controls)

    def handle_af_run(self, body):
        controls = {
            'AfTrigger': True
        }
        self.svr_sock.send_pyobj(controls)

    def handle_lp_increase(self, body):
        if self.lens_position is None:
            return
        
        controls = {
            'LensPosition': self.lens_position*1.1
        }
        self.svr_sock.send_pyobj(controls)

    def handle_lp_decrease(self, body):
        if self.lens_position is None:
            return

        controls = {
            'LensPosition': self.lens_position*0.9
        }
        self.svr_sock.send_pyobj(controls)

    def handle_fit_scaled(self, body):
        controls = {
            'FitMode': 'scaled'
        }
        self.svr_sock.send_pyobj(controls)
    
    def handle_fit_cropped(self, body):
        controls = {
            'FitMode': 'cropped'
        }
        self.svr_sock.send_pyobj(controls)
