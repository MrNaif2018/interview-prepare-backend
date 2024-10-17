import string

EVENTS_CHANNEL = "events"  # default redis channel for event system (inter-process communication)
ALPHABET = string.ascii_letters  # used by ID generator
ID_LENGTH = 32  # default length of IDs of all objects
STR_TO_BOOL_MAPPING = {
    "true": True,
    "yes": True,
    "1": True,
    "false": False,
    "no": False,
    "0": False,
}  # common str -> bool conversions
