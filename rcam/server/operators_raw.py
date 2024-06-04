import cv2
import numpy as np


bayer_codes = {
    'SBGGR10': cv2.COLOR_BayerRG2BGR,
    'SBGGR12': cv2.COLOR_BayerRG2BGR,
    'SBGGR16': cv2.COLOR_BayerRG2BGR,
    'SGRBG16': cv2.COLOR_BayerGB2BGR,
    'SGBRG16': cv2.COLOR_BayerGR2BGR,
    'SRGGB16': cv2.COLOR_BayerBG2BGR,
}

bayer_scale = {
    'SBGGR10': 65535.0/1023.0,
    'SBGGR12': 65535.0/4095.0,
    'SBGGR16': 1.0,
    'SGRBG16': 1.0,
    'SGBRG16': 1.0,
    'SRGGB16': 1.0,
}

image_dtypes = {
    'RGB888': np.uint8,
    'BGR888': np.uint8,
    'SBGGR10': np.uint16,
    'SBGGR12': np.uint16,
    'SBGGR16': np.uint16,
    'SGRBG16': np.uint16,
    'SGBRG16': np.uint16,
    'SRGGB16': np.uint16,
}


def raw_gamma8(pipe):
    
    scale = 255.0 / np.power(65535, 1.0/2.2)

    for item in pipe:
        image = item['raw']['image']
        image_format = item['raw']['format']
        
        # cast the image to the correct type
        image_dtype = image_dtypes[image_format]
        image = image.view(image_dtype)
        
        # scale the image up to the top part of the 16bit word
        image = image * bayer_scale[image_format]

        # subtract the sensor black levels
        black_level = item['metadata']['SensorBlackLevels'][0]
        image = np.maximum(image, black_level) - black_level

        # demosaic the image
        bayer_code = bayer_codes[image_format]
        image = cv2.demosaicing(image.astype(np.uint16), bayer_code)
        
        # apply the gamma encoding and convert to 8bit range
        image = np.power(image, 1.0/2.2) * scale
        image = image.astype(np.uint8)

        # store the image back in the item
        item['raw']['image'] = image

        yield item


def raw_linear8(pipe):
    
    scale = 255.0 / 65535.0

    for item in pipe:
        image = item['raw']['image']
        image_format = item['raw']['format']

        # cast the image to the correct type
        image_dtype = image_dtypes[image_format]
        image = image.view(image_dtype)
        
        # scale the image up to the top part of the 16bit word
        image = image * bayer_scale[image_format]

        # subtract the sensor black levels
        black_level = item['metadata']['SensorBlackLevels'][0]
        image = np.maximum(image, black_level) - black_level

        # demosaic the image
        bayer_code = bayer_codes[image_format]
        image = cv2.demosaicing(image.astype(np.uint16), bayer_code)

        # apply the gamma encoding and convert to 8bit range
        image = image * scale
        image = image.astype(np.uint8)

        # store the image back in the item
        item['raw']['image'] = image

        yield item

