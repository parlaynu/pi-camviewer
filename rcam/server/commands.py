

class ApiCommands:
    SHUTDOWN = 'shutdown'.encode('utf-8')

    SET_SIZE = "set_size".encode('utf-8')

    AUTOEXPOSURE_ENABLE  = "ae_enable".encode('utf-8')
    AUTOEXPOSURE_DISABLE = "ae_disable".encode('utf-8')
    
    ANALOGUE_GAIN_INCREASE = "analogue_gain_increase".encode('utf-8')
    ANALOGUE_GAIN_DECREASE = "analogue_gain_decrease".encode('utf-8')
    
    EXPOSURE_TIME_INCREASE = "exposure_time_increase".encode('utf-8')
    EXPOSURE_TIME_DECREASE = "exposure_time_decrease".encode('utf-8')

    EXPOSURE_LOCKED   = "exposure_locked".encode('utf-8')
    EXPOSURE_UNLOCKED = "exposure_unlocked".encode('utf-8')

    AUTOFOCUS_ENABLE  = "af_enable".encode('utf-8')
    AUTOFOCUS_DISABLE = "af_disable".encode('utf-8')

    AUTOFOCUS_RUN = "af_run".encode('utf-8')
    
    LENS_POSITION_INCREASE = "lens_position_increase".encode('utf-8')
    LENS_POSITION_DECREASE = "lens_position_decrease".encode('utf-8')
    
    FIT_SCALED  = "fit_scaled".encode('utf-8')
    FIT_CROPPED = "fit_cropped".encode('utf-8')


class PubSubCommands:
    METADATA = "metadata".encode('utf-8')
    JPEGIMG  = "jpeg".encode('utf-8')
    RGBIMG   = "rgb".encode('utf-8')

