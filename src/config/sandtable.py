# Constants
HOST_ADDR           = '0.0.0.0'
HOST_PORT           = 80

CACHE_ENABLE        = True
IMAGE_TYPE          = 'Realistic'
LOGGING_LEVEL       = "debug"
SCHEDULER_ENABLE    = True

BALL_SIZE           = 0.75
TABLE_UNITS         = "inches"
TABLE_WIDTH         = 14.0
TABLE_LENGTH        = 11.2

LED_DRIVER          = None
"""
LED_PARAMS          = None
LED_COLUMNS         = 172 
LED_ROWS            = 116
LED_PERIOD          = 1.0 / 45.0
LED_OFFSETS         = [ (1,2), (4,4) ]
LED_MAPPING         = None
"""

MACHINE             = "grbl"
MACHINE_UNITS       = "mm"
MACHINE_FEED        = 2000.0     # mm/minute
MACHINE_ACCEL       = 3000.0

MACHINE_PARAMS = {
    'port': "/dev/ttyUSB0",
    'baud': 115200,
    'init': [
        "$G",
        "$X",
        "$H"
        ]
}
