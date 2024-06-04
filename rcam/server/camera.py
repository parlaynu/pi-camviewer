import os
os.environ['LIBCAMERA_LOG_LEVELS'] = "*:ERROR"

import time
import types

# so we can import the wider package on non-raspberrypi machines
try:
    from picamera2 import Picamera2, Preview
    from libcamera import Transform, ColorSpace, controls
except:
    pass


def Camera(
    camid, 
    mode, 
    *, 
    vflip=False, 
    hflip=False, 
    preview=False, 
    max_fps=0, 
    exposure_time=0, 
    analogue_gain=0.0,
    tuning_file=None,
):

    # check for tuning file override
    tuning = None if tuning_file is None else Picamera2.load_tuning_file(tuning_file)

    cam = Picamera2(camid, tuning=tuning)

    sensor_mode = cam.sensor_modes[mode]
    sensor_format = sensor_mode['unpacked']
    sensor_size = sensor_mode['size']
    sensor_bit_depth = sensor_mode['bit_depth']
    
    # take special care with size if we're previewing
    preview_size = None
    if preview:
        preview_size = (1920, 1080)
        if main_size[0] < preview_size[0] or main_size[1] < preview_size[1]:
            main_size = preview_size

    kwargs = {
        'buffer_count': 3,
        'colour_space': ColorSpace.Sycc(),
        'controls': {
            # 'AwbMode': controls.AwbModeEnum.Daylight,
            'NoiseReductionMode': controls.draft.NoiseReductionModeEnum.HighQuality,
        },
        'main': {
            'size': sensor_size,
            'format': 'BGR888'  # is actually RGB
        },
        'raw': {
            'size': sensor_size,
            'format': str(sensor_format)
        },
        'queue': False
    }

    # some older versions of the library don't support 'sensor'. if it's in
    #   the default configuration, it's ok to include it
    if hasattr(cam.still_configuration, 'sensor'):
        kwargs['sensor'] = {
            'output_size': sensor_size,
            'bit_depth': sensor_bit_depth
        }

    # control the exposure settings
    kwargs['controls']['AeEnable'] = True
    # kwargs['controls']['AeConstraintMode'] = controls.AeConstraintModeEnum.Highlight
    # kwargs['controls']['AeExposureMode'] = controls.AeExposureModeEnum.Long
    kwargs['controls']['AeMeteringMode'] = controls.AeMeteringModeEnum.CentreWeighted

    if exposure_time > 0:
        kwargs['controls']['AeEnable'] = False
        kwargs['controls']['AnalogueGain'] = analogue_gain
        kwargs['controls']['ExposureTime'] = exposure_time
        
    if preview:
        kwargs['lores'] = {
            'size': preview_size
        }
        kwargs['display'] = 'lores'

    if vflip or hflip:
        kwargs['transform'] = Transform(vflip=vflip, hflip=hflip)
    
    config = cam.create_still_configuration(**kwargs)
    cam.align_configuration(config)
    cam.configure(config)
    
    if max_fps > 0:
        minfd, maxfd, _ = cam.camera_controls['FrameDurationLimits']
        minfd = max(minfd, int(1000000/max_fps))
        fd_controls = {
            'FrameDurationLimits': (minfd, maxfd)
        }
        cam.set_controls(fd_controls)
    
    # add some helper methods
    cam.start_preview_ = types.MethodType(start_preview_, cam)
    
    cam.wait_for_aelock_ = types.MethodType(wait_for_aelock_, cam)

    cam.enable_auto_ = types.MethodType(enable_auto_, cam)
    cam.disable_auto_ = types.MethodType(disable_auto_, cam)
    cam.set_exposure_ = types.MethodType(set_exposure_, cam)

    return cam


def start_preview_(self):
    assert False
    self.start_preview(Preview.DRM, width=1920, height=1080)


def wait_for_aelock_(self):
    metadata = {'AeLocked': False}
    while metadata['AeLocked'] == False:
        metadata = self.capture_metadata()


def enable_auto_(self):
    controls = {
        'AeEnable': True,
        'AwbEnable': True
    }
    self.set_controls(controls)


def disable_auto_(self):
    controls = {
        'AeEnable': False,
        'AwbEnable': False
    }
    self.set_controls(controls)


def set_exposure_(self, exposure_time, analogue_gain):
    controls = {
        'ExposureTime': exposure_time,
        'AnalogueGain': analogue_gain
    }
    self.set_controls(controls)

