from itertools import count
import json
import sys
import io
import zmq

from PIL import Image

try:
    from libcamera import controls
except:
    pass

from .commands import PubSubCommands


def control(svr_socket):
    
    for idx in count():
        item = {
            'idx': idx,
            'controls': {}
        }

        while True:
            ev = svr_socket.poll(timeout=0, flags=zmq.POLLIN)
            if ev == 0:
                break
            ctrls = svr_socket.recv_pyobj()
            item['controls'].update(ctrls)

        yield item


def capture(pipe, camera, arrays):
    # get the camera capturing
    job = camera.capture_arrays(arrays, wait=False)    

    # start the main loop
    for item in pipe:
        # wait for the current capture
        images, metadata = camera.wait(job)

        # launch the next capture
        job = camera.capture_arrays(arrays, wait=False)

        # build the item to yield
        item['metadata'] = metadata
        item['metadata']['CameraModel'] = camera.camera_properties['Model']
        item['metadata']['ImageSize'] = camera.camera_config['main']['size']
        
    
        item['main'] = {
            'image': images[0],
            'format': camera.camera_config['main']['format'],
            'framesize': camera.camera_config['main']['framesize'],
            'size': camera.camera_config['main']['size'],
            'stride': camera.camera_config['main']['stride']
        }

        yield item


def focus(pipe, camera):
    
    # start in autofocus mode and trigger a focus run
    ctrls = {
        'AfMode': controls.AfModeEnum.Auto,
        'AfTrigger': controls.AfTriggerEnum.Start
    }
    camera.set_controls(ctrls)
    
    af_enable = True
    
    for item in pipe:
        ctrls = item['controls']
        local_ctrls = {}
        if (ctrl_af_enable := ctrls.get('AfEnable', None)) is not None:
            af_enable = ctrl_af_enable
            if af_enable:
                local_ctrls['AfMode'] = controls.AfModeEnum.Auto
                local_ctrls['AfTrigger'] = controls.AfTriggerEnum.Start
            else:
                af_enable = False
                local_ctrls['AfMode'] = controls.AfModeEnum.Manual
        
        if ctrls.get('AfTrigger', False):
            local_ctrls['AfTrigger'] = controls.AfTriggerEnum.Start
        
        if (lp := ctrls.get('LensPosition', None)) is not None:
            af_enable = False
            local_ctrls['AfMode'] = controls.AfModeEnum.Manual
            local_ctrls['LensPosition'] = lp
        
        if len(local_ctrls):
            camera.set_controls(local_ctrls)
            
        # insert the AfEnable item into the metadata
        metadata = item['metadata']
        metadata['AfEnable'] = af_enable
        
        yield item


def exposure(pipe, camera):
    # the controls managed in this operator
    local_keys = {'AeEnable', 'AwbEnable', 'AnalogueGain', 'ExposureTime'}
    
    ae_enable = True
    
    for item in pipe:
        # set the controls
        ctrls = item['controls']
        local_ctrls = { k: ctrls[k] for k in local_keys & ctrls.keys() }
        if len(local_ctrls):
            camera.set_controls(local_ctrls)

        # insert the AeEnable item into the metadata
        metadata = item['metadata']
        metadata['AeEnable'] = ae_enable = local_ctrls.get('AeEnable', ae_enable)
        
        yield item


def jpeg_encoder(pipe):
    
    for item in pipe:
        image = item['main']['image']

        image = Image.fromarray(image)
        
        jpeg = io.BytesIO()
        image.save(jpeg, format='jpeg', quality=95)
        jpeg.seek(0, io.SEEK_SET)
        
        item['jpeg'] = jpeg.getvalue()
        
        yield item


def publisher(pipe, pub_sock, svr_socket):
    
    exposure_time = 0
    analogue_gain = 0.0
    lens_position = 0.0

    for item in pipe:
        idx = item['idx']
        idx = f"{idx}".encode('utf-8')

        # take a copy of the metadata so we can change it without impacting
        #   any other operators
        metadata = item['metadata'].copy()

        # remove and stats information from the metadata
        for k in list(metadata.keys()):
            if k.endswith('StatsOutput'):
                del metadata[k]
        
        # send the metadata
        metajs = json.dumps(metadata, separators=(',',':'))
        pub_sock.send_multipart([PubSubCommands.METADATA, idx, metajs.encode('utf-8')], copy=False)

        # send the jpeg image
        jpeg = item['jpeg']
        pub_sock.send_multipart([PubSubCommands.JPEGIMG, idx, jpeg], copy=False)
        
        # send updates to the api server
        updates = {}
        
        if metadata['AnalogueGain'] != analogue_gain or metadata['ExposureTime'] != exposure_time:
            analogue_gain = updates['AnalogueGain'] = metadata['AnalogueGain']
            exposure_time = updates['ExposureTime'] = metadata['ExposureTime']
        
        if lens_position != metadata.get('LensPosition', 0.0):
            lens_position = updates['LensPosition'] = metadata['LensPosition']
        
        if len(updates):
            svr_socket.send_pyobj(updates)

        yield item


def fit_cropped(pipe, *, enabled):

    enabled = enabled
    set_crop_w = sys.maxsize
    set_crop_h = sys.maxsize
    
    for item in pipe:
        controls = item['controls']

        # check for updates
        if (fmode := controls.get('FitMode', None)) is not None:
            enabled = (fmode == 'cropped')
        set_crop_w = controls.get('Width', set_crop_w)
        set_crop_h = controls.get('Height', set_crop_h)

        if enabled:
            image = item['main']['image']
            image_h, image_w, _ = image.shape
        
            crop_w, crop_h = min(image_w, set_crop_w), min(image_h, set_crop_h)
        
            if crop_w < image_w or crop_h < image_h:
                x0, x1 = int((image_w - crop_w)/2), int((image_w + crop_w)/2)
                y0, y1 = int((image_h - crop_h)/2), int((image_h + crop_h)/2)
                item['main']['image'] = image[y0:y1, x0:x1, :]

        yield item


def fit_scaled(pipe, *, enabled):
    # shield the client from this requirement
    import cv2

    enabled = enabled
    set_scale_w = sys.maxsize
    set_scale_h = sys.maxsize
    
    for item in pipe:
        controls = item['controls']

        # check for updates
        if (fmode := controls.get('FitMode', None)) is not None:
            enabled = (fmode == 'scaled')
        set_scale_w = controls.get('Width', set_scale_w)
        set_scale_h = controls.get('Height', set_scale_h)

        if enabled:
            image = item['main']['image']
            image_h, image_w, _ = image.shape
        
            scale_w, scale_h = min(image_w, set_scale_w), min(image_h, set_scale_h)
            if scale_w < image_w or scale_h < image_h:
                # preserve image aspect ratio
                scale = min(scale_w/image_w, scale_h/image_h)
                item['main']['image'] = cv2.resize(image, None, fx=scale, fy=scale)

        yield item
